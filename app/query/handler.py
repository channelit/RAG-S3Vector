"""
Query Lambda
============
Accepts: {"query": "your question here"}
Returns: {"answer": "...", "sources": ["s3-key-1", ...]}

Flow:
  1. Embed the incoming query with Bedrock Nova multimodal embeddings
  2. Retrieve top-K nearest vectors from S3 Vectors
  3. Build a prompt using the retrieved context chunks
  4. Call the Bedrock LLM with the guardrail applied
  5. Return the answer and source document keys
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_client = boto3.client("bedrock-runtime")
s3vectors_client = boto3.client("s3vectors")

VECTOR_BUCKET_NAME = os.environ["VECTOR_BUCKET_NAME"]
VECTOR_INDEX_NAME = os.environ["VECTOR_INDEX_NAME"]
EMBEDDING_MODEL_ID = os.environ["EMBEDDING_MODEL_ID"]
LLM_MODEL_ID = os.environ["LLM_MODEL_ID"]
GUARDRAIL_ID = os.environ["GUARDRAIL_ID"]
GUARDRAIL_VERSION = os.environ["GUARDRAIL_VERSION"]

TOP_K = 5
EMBEDDING_DIMENSION = 1024


def embed(text: str) -> list[float]:
    request_body = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_INDEX",
            "embeddingDimension": EMBEDDING_DIMENSION,
            "text": {"truncationMode": "END", "value": text},
        },
    }
    response = bedrock_client.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        body=json.dumps(request_body),
    )
    return json.loads(response["body"].read())["embeddings"][0]["embedding"]


def _build_date_filter(date_from: str | None, date_to: str | None) -> dict | None:
    """Build an S3 Vectors numeric filter on document_timestamp (Unix seconds).

    $gte/$lte only work on Number metadata — that's why we store document_timestamp
    as an int alongside the human-readable document_date string.
    """
    conditions = []
    if date_from:
        ts = int(datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        conditions.append({"document_timestamp": {"$gte": ts}})
    if date_to:
        # include all of date_to day up to 23:59:59 UTC
        ts = int((datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                  + timedelta(days=1) - timedelta(seconds=1)).timestamp())
        conditions.append({"document_timestamp": {"$lte": ts}})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def retrieve(query_embedding: list[float], date_filter: dict | None = None) -> list[dict]:
    logger.info(
        "Querying S3 Vectors bucket=%s index=%s topK=%s embedding_dim=%d filter=%s",
        VECTOR_BUCKET_NAME, VECTOR_INDEX_NAME, TOP_K, len(query_embedding), date_filter,
    )
    kwargs = dict(
        vectorBucketName=VECTOR_BUCKET_NAME,
        indexName=VECTOR_INDEX_NAME,
        topK=TOP_K,
        queryVector={"float32": query_embedding},
        returnMetadata=True,
        returnDistance=True,
    )
    if date_filter:
        kwargs["filter"] = date_filter

    response = s3vectors_client.query_vectors(**kwargs)
    hits = response.get("vectors", [])
    logger.info("Retrieved %d hit(s)", len(hits))
    for i, hit in enumerate(hits):
        logger.info(
            "  hit[%d] key=%s distance=%s metadata_keys=%s",
            i, hit.get("key"), hit.get("distance"), list(hit.get("metadata", {}).keys()),
        )
    return hits


SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the question using only the context provided. "
    "If the answer is not present, say \"I don't have enough information to answer that.\""
)


def build_user_message(query: str, hits: list[dict]) -> str:
    context_blocks = []
    for hit in hits:
        metadata = hit.get("metadata", {}) or {}
        source = metadata.get("source", "unknown")
        text = metadata.get("text", "")
        context_blocks.append(f"[Source: {source}]\n{text}")

    context = "\n\n".join(context_blocks)
    logger.info("Built context with %d block(s), total %d chars", len(context_blocks), len(context))
    return f"<context>\n{context}\n</context>\n\nQuestion: {query}"


def format_llama_prompt(system: str, user: str) -> str:
    return (
        "<|begin_of_text|>"
        f"<|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def _in_date_range(hit: dict, date_from: str | None, date_to: str | None) -> bool:
    doc_date = (hit.get("metadata") or {}).get("document_date", "")
    if not doc_date:
        return True  # no date stored → don't exclude
    day = doc_date[:10]  # "YYYY-MM-DD" prefix is lexicographically comparable
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


def lambda_handler(event, context):
    # Support both direct invocation and API Gateway proxy events
    if "body" in event:
        body = json.loads(event["body"] or "{}")
    else:
        body = event

    query = body.get("query", "").strip()
    if not query:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "query field is required"}),
        }

    date_from = body.get("date_from") or None
    date_to = body.get("date_to") or None

    logger.info("Received query: %r date_from=%s date_to=%s", query, date_from, date_to)
    query_embedding = embed(query)

    # Pre-filter: numeric range on document_timestamp applied inside S3 Vectors ANN search
    date_filter = _build_date_filter(date_from, date_to)
    hits = retrieve(query_embedding, date_filter=date_filter)

    # Post-filter: string-date fallback for vectors ingested before document_timestamp was added
    if date_from or date_to:
        before = len(hits)
        hits = [h for h in hits if _in_date_range(h, date_from, date_to)]
        logger.info("Post-filter (%s → %s): %d → %d hit(s)", date_from, date_to, before, len(hits))

    user_message = build_user_message(query, hits)
    llm_body = json.dumps({
        "prompt": format_llama_prompt(SYSTEM_PROMPT, user_message),
        "max_gen_len": 1024,
        "temperature": 0.3,
        "top_p": 0.9,
    })

    llm_response = bedrock_client.invoke_model(
        modelId=LLM_MODEL_ID,
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        body=llm_body,
    )

    result = json.loads(llm_response["body"].read())
    logger.info(
        "LLM responded; guardrailAction=%s, generation_chars=%d",
        result.get("amazon-bedrock-guardrailAction"),
        len(result.get("generation", "") or ""),
    )

    if result.get("amazon-bedrock-guardrailAction") == "INTERVENED":
        return {
            "statusCode": 200,
            "body": json.dumps(
                {"answer": "Response blocked by content policy.", "sources": []}
            ),
        }

    answer = result["generation"]
    sources = list(
        {
            hit.get("metadata", {}).get("fields", {}).get("source", {}).get("stringValue", "")
            for hit in hits
        }
        - {""}
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"answer": answer, "sources": sources}),
    }
