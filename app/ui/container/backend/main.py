"""FastAPI backend for the container UI.

Queries a Bedrock Knowledge Base in two steps — bedrock-agent-runtime
retrieve() for chunks, then bedrock-runtime converse() to write the answer.

Date filtering: the UI's date range is turned into a `date_numeric`
(YYYYMMDD int) metadata filter on retrieve(). That attribute comes solely
from the scraper's .metadata.json sidecars, which the KB indexes into its
vector store, so the range is enforced inside the vector search. There is
no post-filtering and no other date source (no S3 object tags, no
ingestion-Lambda fields).
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
# Managed knowledge bases don't support RetrieveAndGenerate, so retrieval and
# generation are separate calls: bedrock-agent-runtime retrieve() for chunks,
# then bedrock-runtime converse() to write the answer.
GEN_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
# Optional Bedrock Guardrail applied to generation. GUARDRAIL_ID takes the
# guardrail's ID or ARN (not its name); version is "DRAFT" or a published number.
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID") or None
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")
NUM_RESULTS = int(os.environ.get("KB_NUM_RESULTS", "8"))
# Lifetime of presigned S3 links returned for sources that have no public URL.
SOURCE_URL_TTL_SECONDS = int(os.environ.get("SOURCE_URL_TTL_SECONDS", "3600"))

# Public CSMS bulletin URL: the numeric message ID rendered in lowercase hex
# (CSMS # 69302472 -> .../bulletins/42178c8). Keys written by the scraper look
# like csms/<id>/csms-<id>.txt or csms/<id>/attachments/<file>, optionally
# under an extra batch prefix (csms/1/<id>/...).
BULLETIN_URL_TEMPLATE = "https://content.govdelivery.com/accounts/USDHSCBP/bulletins/{code}"
_CSMS_KEY_RE = re.compile(r"(?:^|/)csms/(?:[^/]+/)*?(\d{6,10})/(?P<rest>.+)$")

bedrock_agent = boto3.client("bedrock-agent-runtime")
bedrock_runtime = boto3.client("bedrock-runtime")
s3 = boto3.client("s3")

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


def _retrieve(query: str, retrieval_filter: dict | None) -> list[dict]:
    """Vector search over the KB. The `date_numeric` filter (when set) is
    applied by the vector store itself, so every result is inside the range."""
    config: dict = {"numberOfResults": NUM_RESULTS}
    if retrieval_filter:
        config["filter"] = retrieval_filter
    response = bedrock_agent.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": config},
    )
    return response.get("retrievalResults", [])


_S3_HOST_RE = re.compile(r"^([^.]+)\.s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com$")


def _s3_bucket_key(uri: str) -> tuple[str, str] | None:
    """(bucket, key) for an s3:// URI or a virtual-hosted S3 https URL
    (the KB reports locations as https://<bucket>.s3.amazonaws.com/<key>)."""
    parsed = urlparse(uri)
    key = unquote(parsed.path.lstrip("/"))
    if parsed.scheme == "s3" and parsed.netloc:
        return parsed.netloc, key
    if parsed.scheme == "https":
        m = _S3_HOST_RE.match(parsed.netloc)
        if m and key:
            return m.group(1), key
    return None


def _s3_uri_url(uri: str) -> str | None:
    """Clickable URL for a KB result's location: the public GovDelivery
    bulletin for CSMS message text, a presigned GET link for any other S3
    object, and non-S3 URLs (archive-PDF-derived pages) as they are."""
    located = _s3_bucket_key(uri)
    if located is None:
        return uri if uri.startswith(("http://", "https://")) else None
    bucket, key = located
    m = _CSMS_KEY_RE.search(key)
    if m and m.group("rest") == f"csms-{m.group(1)}.txt":
        return BULLETIN_URL_TEMPLATE.format(code=f"{int(m.group(1)):x}")
    try:
        return s3.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=SOURCE_URL_TTL_SECONDS
        )
    except (ClientError, BotoCoreError) as exc:  # pragma: no cover - defensive
        logger.warning("Could not presign %s: %s", uri, exc)
        return None


def _source_info(result: dict) -> tuple[str, str | None]:
    """(label, url) for a retrieved chunk. Uses the scraper's sidecar
    attributes (message_id/subject/source_url/sent_date); objects without a
    sidecar (e.g. standalone PDFs) get the KB's own _document_title / _source_uri."""
    meta = result.get("metadata", {})
    url = meta.get("source_url") or meta.get("parent_source_url")
    subject = meta.get("subject") or meta.get("parent_subject")
    message_id = meta.get("message_id")
    sent = meta.get("sent_date")
    if not isinstance(sent, str):
        sent = None
    if url and message_id and subject:
        head = f"CSMS #{message_id} ({sent})" if sent else f"CSMS #{message_id}"
        return f"{head}: {subject}", url
    uri = (
        meta.get("_source_uri")
        or result.get("location", {}).get("s3Location", {}).get("uri")
        or url
        or "unknown source"
    )
    # Without sidecar attributes a CSMS key still yields a useful "CSMS #<id>" label.
    located = _s3_bucket_key(uri)
    m = _CSMS_KEY_RE.search(located[1]) if located else None
    if m:
        title = f"CSMS #{m.group(1)}"
        if m.group("rest") != f"csms-{m.group(1)}.txt":
            title += f" attachment: {m.group('rest').rsplit('/', 1)[-1]}"
        if sent:
            title = f"{title} ({sent})"
        if subject:
            title += f": {subject}"
    else:
        title = subject or meta.get("_document_title")
    return (title or uri), (url or _s3_uri_url(uri))


def _source_label(result: dict) -> str:
    return _source_info(result)[0]


def _generate_answer(query: str, results: list[dict]) -> tuple[str, bool]:
    """Write the answer with converse(), applying the guardrail when
    configured. Returns (answer_text, guardrail_intervened)."""
    passages = []
    for i, result in enumerate(results, 1):
        text = result.get("content", {}).get("text", "")
        passages.append(f"[{i}] (source: {_source_label(result)})\n{text}")
    prompt = "Context passages:\n\n" + "\n\n".join(passages) + f"\n\nQuestion: {query}"

    kwargs: dict = {
        "modelId": GEN_MODEL_ID,
        "system": [{"text": SYSTEM_PROMPT}],
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 1024},
    }
    if GUARDRAIL_ID:
        kwargs["guardrailConfig"] = {
            "guardrailIdentifier": GUARDRAIL_ID,
            "guardrailVersion": GUARDRAIL_VERSION,
        }

    response = bedrock_runtime.converse(**kwargs)
    content = response.get("output", {}).get("message", {}).get("content", [])
    answer = next((block["text"] for block in content if "text" in block), "")
    intervened = response.get("stopReason") == "guardrail_intervened"
    if intervened:
        # answer now carries the guardrail's configured blocked/masked message
        logger.warning("Guardrail %s v%s intervened", GUARDRAIL_ID, GUARDRAIL_VERSION)
    return answer, intervened


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

    date_filtered = from_num is not None or to_num is not None
    try:
        results = _retrieve(req.query, _build_filter(from_num, to_num))
        if date_filtered:
            logger.info("Date range %s..%s: %d result(s)", req.date_from, req.date_to, len(results))
        if not results:
            answer = (
                "No documents found in the selected date range."
                if date_filtered
                else "No matching documents were found in the knowledge base."
            )
            return {"answer": answer, "sources": []}
        answer, guardrail_intervened = _generate_answer(req.query, results)
    except (ClientError, BotoCoreError) as exc:
        logger.error("Knowledge Base query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Knowledge Base query failed: {exc}")

    if guardrail_intervened:
        # Don't cite sources under a blocked/masked answer
        return {"answer": answer or "Response blocked by content policy.", "sources": []}

    sources: list[dict] = []
    seen: set[str] = set()
    for result in results:
        label, url = _source_info(result)
        if label not in seen:
            seen.add(label)
            sources.append({"label": label, "url": url})
    return {"answer": answer, "sources": sources}


# SPA static files — registered last so API routes take precedence
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        return FileResponse(str(STATIC_DIR / "index.html"))
