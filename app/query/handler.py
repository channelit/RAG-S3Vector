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
import os

import boto3

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


def retrieve(query_embedding: list[float]) -> list[dict]:
    response = s3vectors_client.query_vectors(
        vectorBucketName=VECTOR_BUCKET_NAME,
        indexName=VECTOR_INDEX_NAME,
        topK=TOP_K,
        queryVector={"float32": query_embedding},
        returnMetadata=True,
    )
    return response.get("vectors", [])


SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the question using only the context provided. "
    "If the answer is not present, say \"I don't have enough information to answer that.\""
)


def build_user_message(query: str, hits: list[dict]) -> str:
    context_blocks = []
    for hit in hits:
        fields = hit.get("metadata", {}).get("fields", {})
        source = fields.get("source", {}).get("stringValue", "unknown")
        text = fields.get("text", {}).get("stringValue", "")
        context_blocks.append(f"[Source: {source}]\n{text}")

    context = "\n\n".join(context_blocks)
    return f"<context>\n{context}\n</context>\n\nQuestion: {query}"


def format_llama_prompt(system: str, user: str) -> str:
    return (
        "<|begin_of_text|>"
        f"<|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>"
        f"<|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


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

    query_embedding = embed(query)
    hits = retrieve(query_embedding)

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
