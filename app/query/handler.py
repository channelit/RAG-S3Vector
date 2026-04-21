"""
Query Lambda
============
Accepts: {"query": "your question here"}
Returns: {"answer": "...", "sources": ["s3-key-1", ...]}

Flow:
  1. Embed the incoming query with Bedrock Titan Embed Text v2
  2. Retrieve top-K nearest vectors from S3 Vectors
  3. Build a prompt using the retrieved context chunks
  4. Call Bedrock Claude with the guardrail applied
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


def embed(text: str) -> list[float]:
    response = bedrock_client.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        body=json.dumps({"inputText": text}),
    )
    return json.loads(response["body"].read())["embedding"]


def retrieve(query_embedding: list[float]) -> list[dict]:
    response = s3vectors_client.query_vectors(
        vectorBucketName=VECTOR_BUCKET_NAME,
        indexName=VECTOR_INDEX_NAME,
        topK=TOP_K,
        queryVector={"float32Values": query_embedding},
        returnMetadata="ALL_METADATA",
    )
    return response.get("vectors", [])


def build_prompt(query: str, hits: list[dict]) -> str:
    context_blocks = []
    for hit in hits:
        fields = hit.get("metadata", {}).get("fields", {})
        source = fields.get("source", {}).get("stringValue", "unknown")
        text = fields.get("text", {}).get("stringValue", "")
        context_blocks.append(f"[Source: {source}]\n{text}")

    context = "\n\n".join(context_blocks)
    return (
        "You are a helpful assistant. Answer the question using only the context below. "
        "If the answer is not present, say \"I don't have enough information to answer that.\"\n\n"
        f"<context>\n{context}\n</context>\n\n"
        f"Question: {query}\n\nAnswer:"
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

    prompt = build_prompt(query, hits)

    llm_response = bedrock_client.invoke_model(
        modelId=LLM_MODEL_ID,
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }
        ),
    )

    result = json.loads(llm_response["body"].read())

    # Check if the guardrail intervened
    stop_reason = result.get("stop_reason", "")
    if stop_reason == "guardrail_intervened":
        return {
            "statusCode": 200,
            "body": json.dumps(
                {"answer": os.environ.get("BLOCKED_OUTPUT_MSG", "Response blocked by content policy."), "sources": []}
            ),
        }

    answer = result["content"][0]["text"]
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
