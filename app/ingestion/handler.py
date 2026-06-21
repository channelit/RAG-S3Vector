"""
Ingestion Lambda
================
Triggered by S3 ObjectCreated events. For each uploaded document:
  1. Download the object from S3
  2. Split into overlapping text chunks
  3. Generate embeddings via Bedrock Nova Embed
  4. Store vectors + metadata in S3 Vectors

Supported formats: plain text (.txt) and basic PDF text extraction.
For richer PDF/DOCX parsing, add a Lambda layer with pdfminer/python-docx.
"""

import json
import logging
import os
import urllib.parse

import boto3

from archive_pdf_handler import ArchivePdfHandler

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
bedrock_client = boto3.client("bedrock-runtime")
s3vectors_client = boto3.client("s3vectors")

_archive_handler = ArchivePdfHandler(
    s3_client=s3_client,
    bedrock_client=bedrock_client,
    s3vectors_client=s3vectors_client,
    vector_bucket_name=os.environ["VECTOR_BUCKET_NAME"],
    vector_index_name=os.environ["VECTOR_INDEX_NAME"],
    embedding_model_id=os.environ["EMBEDDING_MODEL_ID"],
)

VECTOR_BUCKET_NAME = os.environ["VECTOR_BUCKET_NAME"]
VECTOR_INDEX_NAME = os.environ["VECTOR_INDEX_NAME"]
EMBEDDING_MODEL_ID = os.environ["EMBEDDING_MODEL_ID"]

CHUNK_SIZE = 1000       # characters per chunk
CHUNK_OVERLAP = 200     # overlap between consecutive chunks
BATCH_SIZE = 500        # max vectors per PutVectors call
EMBEDDING_DIMENSION = 1024


def chunk_text(text: str) -> list[str]:
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
    logger.info("Embedding chunk of %d chars with model=%s", len(text), EMBEDDING_MODEL_ID)
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
    logger.info("Embedding produced %d dimensions", len(embedding))
    return embedding


def lambda_handler(event, context):
    logger.info("Ingestion invoked; event=%s", json.dumps(event))
    logger.info(
        "Config: VECTOR_BUCKET=%s VECTOR_INDEX=%s EMBEDDING_MODEL=%s",
        VECTOR_BUCKET_NAME, VECTOR_INDEX_NAME, EMBEDDING_MODEL_ID,
    )

    records = event.get("Records", [])
    logger.info("Processing %d S3 record(s)", len(records))
    processed = 0

    for record in records:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        size = record["s3"]["object"].get("size", "unknown")
        logger.info("--- START s3://%s/%s (size=%s bytes) ---", bucket, key, size)

        # Route archive PDFs to the dedicated handler
        if ArchivePdfHandler.should_handle(key):
            logger.info("Routing to ArchivePdfHandler for archive PDF: %s", key)
            try:
                obj = s3_client.get_object(Bucket=bucket, Key=key)
                last_modified = obj["LastModified"]
                document_date = last_modified.strftime("%Y-%m-%dT%H:%M:%SZ")
                document_timestamp = int(last_modified.timestamp())
                vectors_written = _archive_handler.handle(
                    bucket=bucket,
                    key=key,
                    document_date=document_date,
                    document_timestamp=document_timestamp,
                )
                logger.info("ArchivePdfHandler wrote %d vectors for %s", vectors_written, key)
                processed += 1
            except Exception as e:
                logger.error("ArchivePdfHandler FAILED for %s: %s", key, e)
            continue

        # Standard ingestion path (non-archive or non-PDF)
        try:
            obj = s3_client.get_object(Bucket=bucket, Key=key)
        except Exception as e:
            logger.error("Failed to get object s3://%s/%s: %s", bucket, key, e)
            continue

        raw = obj["Body"].read()
        text = raw.decode("utf-8", errors="ignore")
        last_modified = obj["LastModified"]
        document_date = last_modified.strftime("%Y-%m-%dT%H:%M:%SZ")
        document_timestamp = int(last_modified.timestamp())

        logger.info(
            "Downloaded: bytes=%d decoded_chars=%d content_type=%s "
            "last_modified=%s document_timestamp=%d",
            len(raw), len(text), obj.get("ContentType"),
            document_date, document_timestamp,
        )

        # Chunk
        chunks = chunk_text(text)
        logger.info("Chunked into %d piece(s) (chunk_size=%d overlap=%d)", len(chunks), CHUNK_SIZE, CHUNK_OVERLAP)
        if not chunks:
            logger.warning("No text extracted from s3://%s/%s — skipping", bucket, key)
            continue
        logger.info("First chunk preview (200 chars): %r", chunks[0][:200])

        # Embed + build vector records
        vectors = []
        for i, chunk in enumerate(chunks):
            logger.info("Embedding chunk %d/%d", i + 1, len(chunks))
            embedding = embed(chunk)
            metadata = {
                "source": key,
                "chunk_id": str(i),
                "document_date": document_date,
                "document_timestamp": document_timestamp,
                "text": chunk,
            }
            vector_key = f"{key}#chunk-{i}"
            vectors.append({
                "key": vector_key,
                "data": {"float32": embedding},
                "metadata": metadata,
            })
            logger.info(
                "Built vector key=%s metadata_keys=%s",
                vector_key, list(metadata.keys()),
            )

        # Write to S3 Vectors in batches
        total_written = 0
        for batch_start in range(0, len(vectors), BATCH_SIZE):
            batch = vectors[batch_start: batch_start + BATCH_SIZE]
            logger.info(
                "Calling PutVectors: bucket=%s index=%s batch_size=%d offset=%d",
                VECTOR_BUCKET_NAME, VECTOR_INDEX_NAME, len(batch), batch_start,
            )
            logger.info(
                "Sample vector from batch — key=%s metadata=%s",
                batch[0]["key"],
                {k: v for k, v in batch[0]["metadata"].items() if k != "text"},
            )
            try:
                s3vectors_client.put_vectors(
                    vectorBucketName=VECTOR_BUCKET_NAME,
                    indexName=VECTOR_INDEX_NAME,
                    vectors=batch,
                )
                total_written += len(batch)
                logger.info("PutVectors succeeded: wrote %d vectors (running total=%d)", len(batch), total_written)
            except Exception as e:
                logger.error("PutVectors FAILED at offset=%d: %s", batch_start, e)
                raise

        logger.info(
            "--- END s3://%s/%s: ingested %d chunks, wrote %d vectors ---",
            bucket, key, len(chunks), total_written,
        )
        processed += 1

    logger.info("Ingestion complete: processed %d/%d document(s)", processed, len(records))
    return {"statusCode": 200, "processed_documents": processed}
