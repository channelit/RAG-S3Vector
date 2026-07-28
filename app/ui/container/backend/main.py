import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("uvicorn")

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
# Managed knowledge bases don't support RetrieveAndGenerate, so retrieval and
# generation are separate calls: bedrock-agent-runtime retrieve() for chunks,
# then bedrock-runtime converse() to write the answer.
GEN_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
NUM_RESULTS = int(os.environ.get("KB_NUM_RESULTS", "8"))

bedrock_agent = boto3.client("bedrock-agent-runtime")
bedrock_runtime = boto3.client("bedrock-runtime")

SYSTEM_PROMPT = (
    "You are a compliance assistant answering questions about CBP Cargo Systems "
    "Messaging Service (CSMS) messages. Answer using only the numbered context "
    "passages provided. If the context does not contain the answer, say so. "
    "Be concise and cite the CSMS message numbers you relied on."
)

app = FastAPI(title="RAG Query API")

STATIC_DIR = Path(__file__).parent / "static"


class QueryRequest(BaseModel):
    query: str
    date_from: str | None = None
    date_to: str | None = None


def _date_numeric(value: str) -> int:
    # "2026-07-21" -> 20260721, matching the scraper's date_numeric metadata attribute
    return int(value.replace("-", ""))


def _build_filter(date_from: str | None, date_to: str | None) -> dict | None:
    conditions = []
    if date_from:
        conditions.append({"greaterThanOrEquals": {"key": "date_numeric", "value": _date_numeric(date_from)}})
    if date_to:
        conditions.append({"lessThanOrEquals": {"key": "date_numeric", "value": _date_numeric(date_to)}})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"andAll": conditions}


def _retrieve(query: str, retrieval_filter: dict | None, search_key: str = "managedSearchConfiguration") -> list[dict]:
    search: dict = {"numberOfResults": NUM_RESULTS}
    if retrieval_filter:
        search["filter"] = retrieval_filter
    try:
        response = bedrock_agent.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": query},
            retrievalConfiguration={search_key: search},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ValidationException":
            # Classic (non-managed) KBs take vectorSearchConfiguration instead.
            if search_key == "managedSearchConfiguration" and "managed" in str(exc):
                return _retrieve(query, retrieval_filter, "vectorSearchConfiguration")
            # Some KB types reject metadata filters — retry unfiltered rather than fail the query.
            if retrieval_filter:
                logger.warning("Retrieval filter rejected, retrying without it: %s", exc)
                return _retrieve(query, None, search_key)
        raise
    return response.get("retrievalResults", [])


def _source_label(result: dict) -> str:
    meta = result.get("metadata", {})
    url = meta.get("source_url") or meta.get("parent_source_url")
    subject = meta.get("subject") or meta.get("parent_subject")
    message_id = meta.get("message_id")
    if url:
        return f"CSMS #{message_id}: {subject} — {url}" if message_id and subject else url
    # Managed KBs don't ingest sidecar attributes; fall back to their system metadata.
    uri = (
        meta.get("_source_uri")
        or result.get("location", {}).get("s3Location", {}).get("uri", "unknown source")
    )
    title = meta.get("_document_title")
    return f"{title} — {uri}" if title else uri


def _generate_answer(query: str, results: list[dict]) -> str:
    passages = []
    for i, result in enumerate(results, 1):
        text = result.get("content", {}).get("text", "")
        passages.append(f"[{i}] (source: {_source_label(result)})\n{text}")
    prompt = "Context passages:\n\n" + "\n\n".join(passages) + f"\n\nQuestion: {query}"

    response = bedrock_runtime.converse(
        modelId=GEN_MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 1024},
    )
    return response["output"]["message"]["content"][0]["text"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/query")
def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    try:
        results = _retrieve(req.query, _build_filter(req.date_from, req.date_to))
        if not results:
            return {"answer": "No matching documents were found in the knowledge base.", "sources": []}
        answer = _generate_answer(req.query, results)
    except (ClientError, BotoCoreError) as exc:
        logger.error("Knowledge Base query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Knowledge Base query failed: {exc}")

    sources: list[str] = []
    for result in results:
        label = _source_label(result)
        if label not in sources:
            sources.append(label)
    return {"answer": answer, "sources": sources}


# SPA static files — registered last so API routes take precedence
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        return FileResponse(str(STATIC_DIR / "index.html"))
