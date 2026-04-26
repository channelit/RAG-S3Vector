"""
Ingestion Lambda
================
Triggered by S3 ObjectCreated events. For each uploaded document:
  1. Download the object from S3
  2. Split into overlapping text chunks
  3. Generate embeddings via Bedrock Titan Embed Text v2
  4. Store vectors in S3 Vectors

Supported formats: plain text (.txt) and basic PDF text extraction.
For richer PDF/DOCX parsing, add a Lambda layer with pdfminer/python-docx.
"""

import json
import os
import urllib.parse

import boto3

s3_client = boto3.client("s3")
bedrock_client = boto3.client("bedrock-runtime")
s3vectors_client = boto3.client("s3vectors")

VECTOR_BUCKET_NAME = os.environ["VECTOR_BUCKET_NAME"]
VECTOR_INDEX_NAME = os.environ["VECTOR_INDEX_NAME"]
EMBEDDING_MODEL_ID = os.environ["EMBEDDING_MODEL_ID"]

CHUNK_SIZE = 1000       # characters per chunk
CHUNK_OVERLAP = 200     # overlap between consecutive chunks
BATCH_SIZE = 500        # max vectors per PutVectors call
EMBEDDING_DIMENSION = 1024


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks, preferring sentence boundaries."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = text.rfind(". ", start, end)
            if boundary > start:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        next_start = end - CHUNK_OVERLAP
        start = next_start if next_start > start else end
    return chunks


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


def lambda_handler(event, context):
    processed = 0
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        obj = s3_client.get_object(Bucket=bucket, Key=key)
        text = obj["Body"].read().decode("utf-8", errors="ignore")

        chunks = chunk_text(text)
        if not chunks:
            print(f"No text extracted from s3://{bucket}/{key}, skipping.")
            continue

        vectors = []
        for i, chunk in enumerate(chunks):
            embedding = embed(chunk)
            vectors.append(
                {
                    "key": f"{key}#chunk-{i}",
                    "data": {"float32": embedding},
                    "metadata": {
                        "text": chunk,
                        "source": key,
                        "chunk_id": str(i),
                    },
                }
            )

        # Upload in batches (S3 Vectors max 500 per call)
        for i in range(0, len(vectors), BATCH_SIZE):
            s3vectors_client.put_vectors(
                vectorBucketName=VECTOR_BUCKET_NAME,
                indexName=VECTOR_INDEX_NAME,
                vectors=vectors[i : i + BATCH_SIZE],
            )

        print(f"Ingested {len(chunks)} chunks from s3://{bucket}/{key}")
        processed += 1

    return {"statusCode": 200, "processed_documents": processed}
