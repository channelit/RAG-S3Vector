"""
Query Lambda
============
Accepts: {"query": "...", "date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD"}
Returns: {"answer": "...", "sources": ["s3-key-1", ...]}

Flow:
  1. Embed the incoming query with Bedrock Nova Embed
  2. Pre-filter via S3 Vectors native numeric filter on document_timestamp
  3. Post-filter on document_date string (fallback for older vectors)
  4. Build a prompt from retrieved context chunks
  5. Call the Bedrock LLM with the guardrail applied
  6. Return the answer and source document keys
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
    logger.info("Embedding query (%d chars) with model=%s", len(text), EMBEDDING_MODEL_ID)
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
    embedding = json.loads(response["body"].read())["embeddings"][0]["embedding"]
    logger.info("Query embedding: %d dimensions", len(embedding))
    return embedding


def _build_date_filter(date_from: str | None, date_to: str | None) -> dict | None:
    """Build an S3 Vectors numeric filter on document_timestamp (Unix seconds).

    $gte/$lte only work on Number metadata — that's why we store document_timestamp
    as an int alongside the human-readable document_date string.
    """
    conditions = []
    if date_from:
        ts = int(datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        conditions.append({"document_timestamp": {"$gte": ts}})
        logger.info("Pre-filter: document_timestamp >= %d (%s)", ts, date_from)
    if date_to:
        ts = int((datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                  + timedelta(days=1) - timedelta(seconds=1)).timestamp())
        conditions.append({"document_timestamp": {"$lte": ts}})
        logger.info("Pre-filter: document_timestamp <= %d (%s 23:59:59)", ts, date_to)
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def retrieve(query_embedding: list[float], date_filter: dict | None = None) -> list[dict]:
    logger.info(
        "QueryVectors: bucket=%s index=%s topK=%d embedding_dim=%d filter=%s",
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

    try:
        response = s3vectors_client.query_vectors(**kwargs)
    except Exception as e:
        logger.error("QueryVectors FAILED: %s", e)
        raise

    hits = response.get("vectors", [])
    logger.info("QueryVectors returned %d hit(s)", len(hits))

    for i, hit in enumerate(hits):
        meta = hit.get("metadata") or {}
        logger.info(
            "  hit[%d] key=%s distance=%.4f document_date=%s document_timestamp=%s source=%s text_len=%d",
            i,
            hit.get("key"),
            hit.get("distance") or 0,
            meta.get("document_date", "N/A"),
            meta.get("document_timestamp", "N/A"),
            meta.get("source", "N/A"),
            len(meta.get("text", "")),
        )

    return hits


SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the question using only the context provided. "
    "If the answer is not present, say \"I don't have enough information to answer that.\""
)


def build_user_message(query: str, hits: list[dict]) -> str:
    context_blocks = []
    for hit in hits:
        metadata = hit.get("metadata") or {}
        source = metadata.get("source", "unknown")
        text = metadata.get("text", "")
        context_blocks.append(f"[Source: {source}]\n{text}")

    context = "\n\n".join(context_blocks)
    logger.info("Context: %d block(s), %d total chars", len(context_blocks), len(context))
    return f"<context>\n{context}\n</context>\n\nQuestion: {query}"


def format_llama_prompt(system: str, user: str) -> str:
    return (
        "<|begin_of_text|>"
        f"<|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def _in_date_range(hit: dict, date_from: str | None, date_to: str | None) -> bool:
    """Post-filter fallback — string date comparison for vectors without document_timestamp."""
    doc_date = (hit.get("metadata") or {}).get("document_date", "")
    if not doc_date:
        return True  # no date stored → don't exclude
    day = doc_date[:10]  # "YYYY-MM-DD"
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


def lambda_handler(event, context):
    logger.info("Query Lambda invoked; event=%s", json.dumps(event))
    logger.info(
        "Config: VECTOR_BUCKET=%s VECTOR_INDEX=%s EMBEDDING_MODEL=%s LLM=%s GUARDRAIL=%s v%s",
        VECTOR_BUCKET_NAME, VECTOR_INDEX_NAME, EMBEDDING_MODEL_ID,
        LLM_MODEL_ID, GUARDRAIL_ID, GUARDRAIL_VERSION,
    )

    # Support both direct invocation and API Gateway / Function URL proxy events
    if "body" in event:
        body = json.loads(event["body"] or "{}")
    else:
        body = event

    query = body.get("query", "").strip()
    if not query:
        return {"statusCode": 400, "body": json.dumps({"error": "query field is required"})}

    date_from = body.get("date_from") or None
    date_to = body.get("date_to") or None
    logger.info("Query: %r  date_from=%s  date_to=%s", query, date_from, date_to)

    query_embedding = embed(query)

    # Pre-filter: numeric range on document_timestamp applied inside ANN search
    date_filter = _build_date_filter(date_from, date_to)
    hits = retrieve(query_embedding, date_filter=date_filter)

    # Post-filter: string-date fallback for vectors without document_timestamp
    if date_from or date_to:
        before = len(hits)
        hits = [h for h in hits if _in_date_range(h, date_from, date_to)]
        logger.info("Post-filter (%s → %s): %d → %d hit(s)", date_from, date_to, before, len(hits))

    if not hits:
        logger.warning("No hits after filtering — returning empty answer")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "answer": "No documents found for the specified date range.",
                "sources": [],
            }),
        }

    user_message = build_user_message(query, hits)
    llm_body = json.dumps({
        "prompt": format_llama_prompt(SYSTEM_PROMPT, user_message),
        "max_gen_len": 1024,
        "temperature": 0.3,
        "top_p": 0.9,
    })

    logger.info("Invoking LLM model=%s guardrail=%s", LLM_MODEL_ID, GUARDRAIL_ID)
    llm_response = bedrock_client.invoke_model(
        modelId=LLM_MODEL_ID,
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        body=llm_body,
    )

    result = json.loads(llm_response["body"].read())
    guardrail_action = result.get("amazon-bedrock-guardrailAction")
    generation = result.get("generation", "") or ""
    logger.info("LLM response: guardrailAction=%s generation_chars=%d", guardrail_action, len(generation))

    if guardrail_action == "INTERVENED":
        logger.warning("Guardrail intervened — blocking response")
        return {
            "statusCode": 200,
            "body": json.dumps({"answer": "Response blocked by content policy.", "sources": []}),
        }

    # S3 Vectors metadata is plain JSON — access source directly, not via typed fields
    sources = sorted({
        (hit.get("metadata") or {}).get("source", "")
        for hit in hits
    } - {""})
    logger.info("Returning answer (%d chars) with %d source(s): %s", len(generation), len(sources), sources)

    return {
        "statusCode": 200,
        "body": json.dumps({"answer": generation, "sources": sources}),
    }
