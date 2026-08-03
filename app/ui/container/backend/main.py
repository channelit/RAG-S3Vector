"""FastAPI backend for the container UI.

Queries a Bedrock Knowledge Base in two steps — bedrock-agent-runtime
retrieve() for chunks, then bedrock-runtime converse() to write the answer.

Date filtering strategy (the UI's date range must be authoritative):
  1. Pre-filter: a `date_numeric` (YYYYMMDD int, from the scraper's
     .metadata.json sidecars) metadata filter is passed to retrieve(). KBs
     that index sidecar attributes into their vector store (e.g. an
     S3 Vectors-backed KB) enforce the range inside the vector search.
  2. Post-filter: results are re-checked against the range using whatever
     date metadata they carry. Results outside the range — or carrying no
     date metadata at all (managed KBs don't ingest sidecars) — are dropped,
     so a chunk can never be cited outside the requested dates.
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError, ParamValidationError
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
# When the KB can't enforce the date filter natively, fetch deeper so the
# post-filter has enough candidates left after dropping out-of-range chunks.
UNFILTERED_NUM_RESULTS = max(NUM_RESULTS, 25)

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


# Retrieval strategy that succeeded last ("vector" | "managed" | "bare"),
# cached so every request doesn't re-pay the failed probe calls.
_working_strategy: str | None = None
_STRATEGY_ORDER = ("vector", "managed", "bare")


def _retrieve(query: str, retrieval_filter: dict | None) -> tuple[list[dict], bool]:
    """Query the KB, degrading gracefully across KB types.

    Attempts, in order: vectorSearchConfiguration with the metadata filter
    (classic KBs — incl. S3 Vectors-backed ones — enforce the date range
    inside the vector search), vectorSearchConfiguration without the filter,
    managedSearchConfiguration (managed KBs reject vectorSearch; the param
    only exists in newer botocore, so ParamValidationError is tolerated),
    then a bare retrieve with no retrievalConfiguration at all.

    Returns (results, filter_enforced) so the caller knows whether the date
    range was already applied in-store.
    """
    global _working_strategy

    attempts: list[tuple[str, dict | None, bool]] = []
    if retrieval_filter:
        attempts.append((
            "vector",
            {"vectorSearchConfiguration": {"numberOfResults": NUM_RESULTS, "filter": retrieval_filter}},
            True,
        ))
        attempts.append(
            ("vector", {"vectorSearchConfiguration": {"numberOfResults": UNFILTERED_NUM_RESULTS}}, False)
        )
    else:
        attempts.append(("vector", {"vectorSearchConfiguration": {"numberOfResults": NUM_RESULTS}}, False))
    attempts.append(("managed", {"managedSearchConfiguration": {"numberOfResults": NUM_RESULTS}}, False))
    attempts.append(("bare", None, False))

    # Skip strategies already known to fail for this KB.
    if _working_strategy in _STRATEGY_ORDER:
        floor = _STRATEGY_ORDER.index(_working_strategy)
        attempts = [a for a in attempts if _STRATEGY_ORDER.index(a[0]) >= floor]

    last_exc: Exception | None = None
    for strategy, config, filter_enforced in attempts:
        kwargs: dict = {
            "knowledgeBaseId": KNOWLEDGE_BASE_ID,
            "retrievalQuery": {"text": query},
        }
        if config is not None:
            kwargs["retrievalConfiguration"] = config
        try:
            response = bedrock_agent.retrieve(**kwargs)
        except ParamValidationError as exc:
            # This botocore doesn't model the parameter (e.g. managedSearchConfiguration)
            logger.warning("KB retrieve config not supported by this SDK (%s): %s", strategy, exc)
            last_exc = exc
            continue
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ValidationException":
                raise
            logger.warning("KB retrieve rejected %s config: %s", strategy, exc)
            last_exc = exc
            continue
        _working_strategy = strategy
        if retrieval_filter and not filter_enforced:
            logger.warning(
                "KB did not enforce the date filter natively — post-filter will drop out-of-range results"
            )
        return response.get("retrievalResults", []), filter_enforced

    _working_strategy = None
    raise last_exc


def _result_date_numeric(result: dict) -> int | None:
    """Best-effort YYYYMMDD for a result, from any date attribute either
    ingestion pipeline writes (scraper sidecars or the S3 Vectors Lambda)."""
    meta = result.get("metadata") or {}
    value = meta.get("date_numeric")
    if value is not None:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            pass
    for key in ("sent_date", "document_date"):
        raw = meta.get(key)
        if isinstance(raw, str) and len(raw) >= 10:
            try:
                return int(raw[:10].replace("-", ""))
            except ValueError:
                pass
    for key in ("timestamp", "document_timestamp"):
        raw = meta.get(key)
        if raw is not None:
            try:
                return int(datetime.fromtimestamp(int(float(raw)), tz=timezone.utc).strftime("%Y%m%d"))
            except (TypeError, ValueError, OSError, OverflowError):
                pass
    return None


def _apply_date_range(
    results: list[dict], from_num: int | None, to_num: int | None
) -> tuple[list[dict], int, int]:
    """Keep only results provably inside the range. Results with no date
    metadata can't be verified, so they are excluded rather than shown."""
    kept: list[dict] = []
    out_of_range = 0
    undated = 0
    for result in results:
        day = _result_date_numeric(result)
        if day is None:
            undated += 1
        elif (from_num is not None and day < from_num) or (to_num is not None and day > to_num):
            out_of_range += 1
        else:
            kept.append(result)
    return kept, out_of_range, undated


def _source_label(result: dict) -> str:
    meta = result.get("metadata", {})
    url = meta.get("source_url") or meta.get("parent_source_url")
    subject = meta.get("subject") or meta.get("parent_subject")
    message_id = meta.get("message_id")
    sent = meta.get("sent_date")
    if not isinstance(sent, str):
        day = _result_date_numeric(result)
        sent = f"{day // 10000:04d}-{day // 100 % 100:02d}-{day % 100:02d}" if day else None
    if url:
        if message_id and subject:
            head = f"CSMS #{message_id} ({sent})" if sent else f"CSMS #{message_id}"
            return f"{head}: {subject} — {url}"
        return url
    # Managed KBs don't ingest sidecar attributes; fall back to their system metadata.
    uri = (
        meta.get("_source_uri")
        or result.get("location", {}).get("s3Location", {}).get("uri", "unknown source")
    )
    title = meta.get("_document_title")
    return f"{title} — {uri}" if title else uri


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

    try:
        results, filter_enforced = _retrieve(req.query, _build_filter(from_num, to_num))

        if from_num is not None or to_num is not None:
            results, out_of_range, undated = _apply_date_range(results, from_num, to_num)
            logger.info(
                "Date range %s..%s (pre-filter %s): kept %d, dropped %d out-of-range, %d undated",
                req.date_from, req.date_to, "enforced" if filter_enforced else "not enforced",
                len(results), out_of_range, undated,
            )
            if not results:
                answer = "No documents found in the selected date range."
                if undated:
                    answer += (
                        f" ({undated} retrieved result(s) carried no date metadata and were excluded — "
                        "the knowledge base may not be indexing the .metadata.json sidecar attributes.)"
                    )
                return {"answer": answer, "sources": []}

        if not results:
            return {"answer": "No matching documents were found in the knowledge base.", "sources": []}
        answer, guardrail_intervened = _generate_answer(req.query, results)
    except (ClientError, BotoCoreError) as exc:
        logger.error("Knowledge Base query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Knowledge Base query failed: {exc}")

    if guardrail_intervened:
        # Don't cite sources under a blocked/masked answer
        return {"answer": answer or "Response blocked by content policy.", "sources": []}

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
