"""FastAPI backend for the container UI.

One Bedrock Knowledge Base RetrieveAndGenerate call per question: the KB
retrieves the chunks (the UI date range becomes a `date_numeric` YYYYMMDD
metadata filter — the attribute the scraper writes into each document's
.metadata.json sidecar) and Bedrock writes the answer from them with the
configured model, applying the guardrail when one is set. Sources come from
the response citations.
"""

import logging
import os
import re
from urllib.parse import unquote, urlparse
from datetime import datetime
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("uvicorn")

KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
bedrock_agent = boto3.client("bedrock-agent-runtime")
REGION = bedrock_agent.meta.region_name or "us-east-1"
# Generation model for RetrieveAndGenerate: a foundation-model / inference-profile
# ARN, or a bare foundation model ID (turned into a foundation-model ARN).
_MODEL = (
    os.environ.get("BEDROCK_MODEL_ARN")
    or os.environ.get("BEDROCK_MODEL_ID")
    or "anthropic.claude-sonnet-4-6"
)
MODEL_ARN = _MODEL if _MODEL.startswith("arn:") else f"arn:aws:bedrock:{REGION}::foundation-model/{_MODEL}"
# Optional Bedrock Guardrail applied to generation: the guardrail's ID (not its
# name); version is "DRAFT" or a published number.
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID") or None
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")
NUM_RESULTS = int(os.environ.get("KB_NUM_RESULTS", "8"))

# Public CSMS bulletin URL: the numeric message ID rendered in lowercase hex
# (CSMS # 69302472 -> .../bulletins/42178c8). Document locations reported in
# citations look like .../csms/<id>/csms-<id>.txt or .../csms/<id>/attachments/<file>,
# optionally under an extra batch prefix (csms/1/<id>/...).
BULLETIN_URL_TEMPLATE = "https://content.govdelivery.com/accounts/USDHSCBP/bulletins/{code}"
_CSMS_KEY_RE = re.compile(r"(?:^|/)csms/(?:[^/]+/)*?(\d{6,10})/(?P<rest>.+)$")

app = FastAPI(title="RAG Query API")

STATIC_DIR = Path(__file__).parent / "static"


class QueryRequest(BaseModel):
    query: str
    date_from: str | None = None
    date_to: str | None = None


def _date_numeric(value: str, field: str) -> int:
    # "2026-07-21" -> 20260721, matching the scraper's date_numeric metadata attribute
    try:
        return int(datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field} must be a valid YYYY-MM-DD date")


def _build_filter(from_num: int | None, to_num: int | None) -> dict | None:
    conditions = []
    if from_num is not None:
        conditions.append({"greaterThanOrEquals": {"key": "date_numeric", "value": from_num}})
    if to_num is not None:
        conditions.append({"lessThanOrEquals": {"key": "date_numeric", "value": to_num}})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"andAll": conditions}


def _retrieve_and_generate(query: str, retrieval_filter: dict | None) -> dict:
    vector_search: dict = {"numberOfResults": NUM_RESULTS}
    if retrieval_filter:
        vector_search["filter"] = retrieval_filter
    kb_config: dict = {
        "knowledgeBaseId": KNOWLEDGE_BASE_ID,
        "modelArn": MODEL_ARN,
        "retrievalConfiguration": {"vectorSearchConfiguration": vector_search},
    }
    if GUARDRAIL_ID:
        kb_config["generationConfiguration"] = {
            "guardrailConfiguration": {"guardrailId": GUARDRAIL_ID, "guardrailVersion": GUARDRAIL_VERSION}
        }
    return bedrock_agent.retrieve_and_generate(
        input={"text": query},
        retrieveAndGenerateConfiguration={"type": "KNOWLEDGE_BASE", "knowledgeBaseConfiguration": kb_config},
    )


def _document_path(reference: dict) -> str:
    """Path part of the citation's document location (any location type)."""
    location = reference.get("location") or {}
    for value in location.values():
        if isinstance(value, dict) and value.get("uri"):
            return unquote(urlparse(value["uri"]).path)
        if isinstance(value, dict) and value.get("url"):
            return value["url"]
    return ""


def _source_info(reference: dict) -> tuple[str, str | None]:
    """(label, url) for a cited chunk. Uses the scraper's sidecar attributes
    (message_id/subject/source_url/sent_date) when the KB exposes them; a CSMS
    document path still yields a "CSMS #<id>" label and its bulletin URL."""
    meta = reference.get("metadata") or {}
    url = meta.get("source_url") or meta.get("parent_source_url")
    subject = meta.get("subject") or meta.get("parent_subject")
    message_id = meta.get("message_id")
    sent = meta.get("sent_date") if isinstance(meta.get("sent_date"), str) else None
    if url and message_id and subject:
        head = f"CSMS #{message_id} ({sent})" if sent else f"CSMS #{message_id}"
        return f"{head}: {subject}", url

    path = _document_path(reference)
    m = _CSMS_KEY_RE.search(path)
    if m:
        message_id = m.group(1)
        title = f"CSMS #{message_id}"
        if m.group("rest") == f"csms-{message_id}.txt":
            url = url or BULLETIN_URL_TEMPLATE.format(code=f"{int(message_id):x}")
        else:
            title += f" attachment: {m.group('rest').rsplit('/', 1)[-1]}"
            url = url or meta.get("attachment_url")
        if sent:
            title = f"{title} ({sent})"
        if subject:
            title += f": {subject}"
        return title, url
    title = subject or meta.get("_document_title") or path.rsplit("/", 1)[-1] or "unknown source"
    return title, (url if url else (path if path.startswith("http") else None))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/query")
def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    from_num = _date_numeric(req.date_from, "date_from") if req.date_from else None
    to_num = _date_numeric(req.date_to, "date_to") if req.date_to else None
    if from_num is not None and to_num is not None and from_num > to_num:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")

    try:
        response = _retrieve_and_generate(req.query, _build_filter(from_num, to_num))
    except (ClientError, BotoCoreError) as exc:
        logger.error("Knowledge Base RetrieveAndGenerate failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Knowledge Base query failed: {exc}")

    answer = (response.get("output") or {}).get("text", "")
    if response.get("guardrailAction") == "INTERVENED":
        # Don't cite sources under a blocked/masked answer
        logger.warning("Guardrail %s v%s intervened", GUARDRAIL_ID, GUARDRAIL_VERSION)
        return {"answer": answer or "Response blocked by content policy.", "sources": []}

    sources: list[dict] = []
    seen: set[str] = set()
    for citation in response.get("citations", []):
        for reference in citation.get("retrievedReferences", []):
            label, url = _source_info(reference)
            if label not in seen:
                seen.add(label)
                sources.append({"label": label, "url": url})
    if from_num is not None or to_num is not None:
        logger.info("Date range %s..%s: %d cited source(s)", req.date_from, req.date_to, len(sources))
    return {"answer": answer, "sources": sources}


# SPA static files — registered last so API routes take precedence
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        return FileResponse(str(STATIC_DIR / "index.html"))
