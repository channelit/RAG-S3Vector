"""FastAPI backend for the container UI.

Answers queries with a guardrailed Bedrock Converse tool loop over the S3
Vectors store — no Knowledge Base, no extra data stores. The LLM decides per
question which tools to call:

  search_messages  — semantic retrieval: embed the query with the Bedrock
                     embedding model, query the S3 Vectors index (topK, with
                     a native numeric pre-filter on document_timestamp), and
                     return the matching passages.
  count_messages   — exact aggregation: counts distinct documents in the
                     corpus from an in-memory manifest built by paging
                     s3vectors ListVectors and deduplicating chunks by their
                     `source` metadata. Supports date-range and keyword
                     filters (keyword matches run over the full stored chunk
                     text, so counts are exhaustive, not topK-limited).

The manifest is cached in memory with a TTL instead of being persisted to S3
— writing a manifest object into the documents bucket would re-trigger the
ingestion Lambda on every refresh.

Date filtering (the UI's date range must be authoritative): the range from
the request clamps every tool call — the model can narrow it but never widen
it. search_messages pre-filters inside the vector search on
document_timestamp and strictly post-filters (undated chunks are excluded
when a range is set); count_messages filters the manifest the same way.

The guardrail (GUARDRAIL_ID/GUARDRAIL_VERSION) is applied on every converse
call; if it intervenes the answer is replaced and no sources are returned.
"""

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("uvicorn")

VECTOR_BUCKET_NAME = os.environ["VECTOR_BUCKET_NAME"]
VECTOR_INDEX_NAME = os.environ["VECTOR_INDEX_NAME"]
EMBEDDING_MODEL_ID = os.environ.get(
    "EMBEDDING_MODEL_ID", "amazon.nova-2-multimodal-embeddings-v1:0"
)
# Generation model for converse() — must support Converse tool use.
GEN_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
# Optional Bedrock Guardrail applied to generation. GUARDRAIL_ID takes the
# guardrail's ID or ARN (not its name); version is "DRAFT" or a published number.
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID") or None
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")

SEARCH_TOP_K = int(os.environ.get("SEARCH_TOP_K", "8"))
EMBEDDING_DIMENSION = 1024
MANIFEST_TTL_SECONDS = int(os.environ.get("MANIFEST_TTL_SECONDS", "600"))
MAX_TOOL_TURNS = int(os.environ.get("MAX_TOOL_TURNS", "8"))
# Optional: the S3 documents bucket the ingestion Lambda reads from. When set,
# sources that have no public URL (attachments, standalone PDFs) are returned
# as presigned GET links so the UI can open them.
DOCUMENTS_BUCKET_NAME = os.environ.get("DOCUMENTS_BUCKET_NAME") or None
SOURCE_URL_TTL_SECONDS = int(os.environ.get("SOURCE_URL_TTL_SECONDS", "3600"))

bedrock_runtime = boto3.client("bedrock-runtime")
s3vectors = boto3.client("s3vectors")
s3 = boto3.client("s3") if DOCUMENTS_BUCKET_NAME else None

# Public CSMS bulletin URL: the numeric message ID rendered in lowercase hex
# (CSMS # 69302472 -> .../bulletins/42178c8). Keys written by the scraper look
# like csms/<id>/csms-<id>.txt or csms/<id>/attachments/<file>, optionally
# under an extra batch prefix (csms/1/<id>/...).
BULLETIN_URL_TEMPLATE = "https://content.govdelivery.com/accounts/USDHSCBP/bulletins/{code}"
_CSMS_KEY_RE = re.compile(r"(?:^|/)csms/(?:[^/]+/)*?(\d{6,10})/(?P<rest>.+)$")


def _source_url(source: str) -> str | None:
    """Best-effort clickable URL for a vector's `source` metadata value."""
    if source.startswith(("http://", "https://")):
        return source  # archive-PDF-derived pages store the fetched URL directly
    m = _CSMS_KEY_RE.search(source)
    bulletin_url = BULLETIN_URL_TEMPLATE.format(code=f"{int(m.group(1)):x}") if m else None
    # The message text itself is best read on the public bulletin page.
    if m and m.group("rest") == f"csms-{m.group(1)}.txt":
        return bulletin_url
    if s3 is not None:
        try:
            return s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": DOCUMENTS_BUCKET_NAME, "Key": source},
                ExpiresIn=SOURCE_URL_TTL_SECONDS,
            )
        except (ClientError, BotoCoreError) as exc:  # pragma: no cover - defensive
            logger.warning("Could not presign %s: %s", source, exc)
    return bulletin_url  # attachment with no bucket configured -> parent bulletin

SYSTEM_PROMPT = (
    "You are a compliance assistant answering questions about CBP Cargo Systems "
    "Messaging Service (CSMS) messages.\n"
    "- For questions about message content, use search_messages and answer only "
    "from the returned passages, citing the source of each fact.\n"
    "- For 'how many' / aggregation questions, use count_messages — its counts "
    "are exact over the whole corpus. Never estimate counts from search results.\n"
    "- Keyword counts match literal text, so phrase them as 'N messages mention "
    "…'; pick a few likely keyword variants when the topic has synonyms.\n"
    "- If neither tool returns the needed information, say so plainly. "
    "Be concise."
)

app = FastAPI(title="RAG Query API")

STATIC_DIR = Path(__file__).parent / "static"


class QueryRequest(BaseModel):
    query: str
    date_from: str | None = None
    date_to: str | None = None


class ToolInputError(Exception):
    """Invalid tool input from the model — returned as an error toolResult."""


# ---------------------------------------------------------------------------
# Dates. YYYYMMDD ints throughout; the vector store pre-filters on the Unix
# document_timestamp, so both representations get built from the same bounds.
# ---------------------------------------------------------------------------


def _parse_day(value: str) -> int:
    # "2026-07-21" -> 20260721
    try:
        return int(datetime.strptime(value, "%Y-%m-%d").strftime("%Y%m%d"))
    except ValueError:
        raise ToolInputError(f"{value!r} is not a valid YYYY-MM-DD date")


def _day_to_timestamp(day: int, end_of_day: bool) -> int:
    dt = datetime.strptime(str(day), "%Y%m%d").replace(tzinfo=timezone.utc)
    if end_of_day:
        dt = dt + timedelta(days=1) - timedelta(seconds=1)
    return int(dt.timestamp())


def _clamp_range(
    tool_from: str | None, tool_to: str | None, ui_from: int | None, ui_to: int | None
) -> tuple[int | None, int | None]:
    """Intersect a model-supplied range with the UI's range — the model may
    narrow the user's filter but never widen it."""
    lo = _parse_day(tool_from) if tool_from else None
    hi = _parse_day(tool_to) if tool_to else None
    if ui_from is not None:
        lo = ui_from if lo is None else max(lo, ui_from)
    if ui_to is not None:
        hi = ui_to if hi is None else min(hi, ui_to)
    return lo, hi


def _metadata_day(meta: dict) -> int | None:
    """YYYYMMDD from a vector's metadata (document_timestamp, else the
    document_date ISO string), or None when undated."""
    ts = meta.get("document_timestamp")
    if ts is not None:
        try:
            return int(
                datetime.fromtimestamp(int(float(ts)), tz=timezone.utc).strftime("%Y%m%d")
            )
        except (TypeError, ValueError, OSError, OverflowError):
            pass
    raw = meta.get("document_date")
    if isinstance(raw, str) and len(raw) >= 10:
        try:
            return int(raw[:10].replace("-", ""))
        except ValueError:
            pass
    return None


def _day_str(day: int | None) -> str | None:
    if day is None:
        return None
    return f"{day // 10000:04d}-{day // 100 % 100:02d}-{day % 100:02d}"


# ---------------------------------------------------------------------------
# Corpus manifest — one entry per distinct document, built from ListVectors.
# ---------------------------------------------------------------------------


@dataclass
class Document:
    source: str
    day: int | None = None  # YYYYMMDD
    chunk_count: int = 0
    text_lower: str = ""


@dataclass
class Manifest:
    documents: list[Document] = field(default_factory=list)
    total_vectors: int = 0
    built_at: float = 0.0
    has_text: bool = False


_manifest: Manifest | None = None
_manifest_lock = threading.Lock()


def _build_manifest() -> Manifest:
    docs: dict[str, Document] = {}
    total = 0
    next_token = None
    while True:
        kwargs = dict(
            vectorBucketName=VECTOR_BUCKET_NAME,
            indexName=VECTOR_INDEX_NAME,
            returnMetadata=True,
            maxResults=500,
        )
        if next_token:
            kwargs["nextToken"] = next_token
        response = s3vectors.list_vectors(**kwargs)
        for vector in response.get("vectors", []):
            total += 1
            meta = vector.get("metadata") or {}
            source = meta.get("source") or vector.get("key", "").split("#chunk-")[0]
            if not source:
                continue
            doc = docs.get(source)
            if doc is None:
                doc = docs[source] = Document(source=source)
            doc.chunk_count += 1
            if doc.day is None:
                doc.day = _metadata_day(meta)
            text = meta.get("text")
            if isinstance(text, str) and text:
                doc.text_lower += " " + text.lower()

        next_token = response.get("nextToken")
        if not next_token:
            break

    manifest = Manifest(
        documents=list(docs.values()),
        total_vectors=total,
        built_at=time.monotonic(),
        has_text=any(doc.text_lower for doc in docs.values()),
    )
    logger.info(
        "Manifest built: %d document(s) from %d vector(s), %d undated, text=%s",
        len(manifest.documents), total,
        sum(1 for d in manifest.documents if d.day is None), manifest.has_text,
    )
    return manifest


def _get_manifest() -> Manifest:
    global _manifest
    with _manifest_lock:
        if _manifest is None or time.monotonic() - _manifest.built_at > MANIFEST_TTL_SECONDS:
            _manifest = _build_manifest()
        return _manifest


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _embed(text: str) -> list[float]:
    request_body = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_INDEX",
            "embeddingDimension": EMBEDDING_DIMENSION,
            "text": {"truncationMode": "END", "value": text},
        },
    }
    response = bedrock_runtime.invoke_model(
        modelId=EMBEDDING_MODEL_ID, body=json.dumps(request_body)
    )
    return json.loads(response["body"].read())["embeddings"][0]["embedding"]


def _search_messages(query: str, from_num: int | None, to_num: int | None) -> dict:
    embedding = _embed(query)
    kwargs = dict(
        vectorBucketName=VECTOR_BUCKET_NAME,
        indexName=VECTOR_INDEX_NAME,
        topK=SEARCH_TOP_K,
        queryVector={"float32": embedding},
        returnMetadata=True,
        returnDistance=True,
    )
    conditions = []
    if from_num is not None:
        conditions.append({"document_timestamp": {"$gte": _day_to_timestamp(from_num, False)}})
    if to_num is not None:
        conditions.append({"document_timestamp": {"$lte": _day_to_timestamp(to_num, True)}})
    if conditions:
        kwargs["filter"] = conditions[0] if len(conditions) == 1 else {"$and": conditions}

    hits = s3vectors.query_vectors(**kwargs).get("vectors", [])

    results = []
    excluded_undated = 0
    for hit in hits:
        meta = hit.get("metadata") or {}
        day = _metadata_day(meta)
        if from_num is not None or to_num is not None:
            # Strict enforcement: with a range set, undated or out-of-range
            # chunks are never shown (older vectors may lack the numeric field
            # the pre-filter uses).
            if day is None:
                excluded_undated += 1
                continue
            if (from_num is not None and day < from_num) or (to_num is not None and day > to_num):
                continue
        results.append({
            "source": meta.get("source", hit.get("key", "unknown")),
            "date": _day_str(day),
            "text": meta.get("text", ""),
        })

    logger.info(
        "search_messages(%r, %s..%s): %d hit(s), kept %d (%d undated excluded)",
        query, _day_str(from_num), _day_str(to_num), len(hits), len(results), excluded_undated,
    )
    payload: dict = {"results": results}
    if not results:
        payload["note"] = "No matching passages found for this query and date range."
    return payload


def _count_messages(
    from_num: int | None, to_num: int | None, keywords: list[str], match: str
) -> dict:
    manifest = _get_manifest()
    range_set = from_num is not None or to_num is not None

    undated_excluded = 0
    candidates = []
    for doc in manifest.documents:
        if range_set:
            if doc.day is None:
                undated_excluded += 1
                continue
            if (from_num is not None and doc.day < from_num) or (
                to_num is not None and doc.day > to_num
            ):
                continue
        candidates.append(doc)

    terms = [k.strip().lower() for k in keywords if k and k.strip()]
    if terms:
        combine = any if match == "any" else all
        matched = [d for d in candidates if combine(t in d.text_lower for t in terms)]
    else:
        matched = candidates

    matched.sort(key=lambda d: d.day or 0, reverse=True)
    by_year: dict[str, int] = {}
    for doc in matched:
        year = str(doc.day)[:4] if doc.day else "undated"
        by_year[year] = by_year.get(year, 0) + 1

    result: dict = {
        "total_messages": len(matched),
        "date_from": _day_str(from_num),
        "date_to": _day_str(to_num),
        "keywords": terms or None,
        "keyword_match": match if terms else None,
        "by_year": by_year,
        "sample_sources": [
            {"source": d.source, "date": _day_str(d.day)} for d in matched[:10]
        ],
        "corpus_total_messages": len(manifest.documents),
    }
    if range_set and undated_excluded:
        result["undated_messages_excluded_by_date_filter"] = undated_excluded
    if terms and not manifest.has_text:
        result["warning"] = (
            "The vector index returned no chunk text, so the keyword filter "
            "matched nothing reliable — treat this count as unavailable."
        )
    logger.info("count_messages(%s..%s, keywords=%s, match=%s): %d of %d document(s)",
                _day_str(from_num), _day_str(to_num), terms, match,
                len(matched), len(manifest.documents))
    return result


TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "search_messages",
                "description": (
                    "Semantic search over CSMS message content. Returns the most "
                    "relevant text passages with their source and date. Use for "
                    "questions about what messages say. Results are limited to "
                    f"the top {SEARCH_TOP_K} passages — never count from them."
                ),
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query, phrased for semantic similarity.",
                        },
                        "date_from": {
                            "type": "string",
                            "description": "Optional YYYY-MM-DD lower bound (inclusive).",
                        },
                        "date_to": {
                            "type": "string",
                            "description": "Optional YYYY-MM-DD upper bound (inclusive).",
                        },
                    },
                    "required": ["query"],
                }},
            }
        },
        {
            "toolSpec": {
                "name": "count_messages",
                "description": (
                    "Exactly count distinct CSMS messages in the corpus, with an "
                    "optional date range and optional keyword filter (a message "
                    "matches when its full text contains the keywords, "
                    "case-insensitive). Counts cover the entire corpus. Use for "
                    "every 'how many' or aggregation question."
                ),
                "inputSchema": {"json": {
                    "type": "object",
                    "properties": {
                        "date_from": {
                            "type": "string",
                            "description": "Optional YYYY-MM-DD lower bound (inclusive).",
                        },
                        "date_to": {
                            "type": "string",
                            "description": "Optional YYYY-MM-DD upper bound (inclusive).",
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional literal keywords/phrases to filter by, "
                                "e.g. [\"china\", \"section 301\"]."
                            ),
                        },
                        "match": {
                            "type": "string",
                            "enum": ["all", "any"],
                            "description": "Whether a message must contain all keywords or any (default all).",
                        },
                    },
                }},
            }
        },
    ]
}


# ---------------------------------------------------------------------------
# Converse tool loop
# ---------------------------------------------------------------------------


def _execute_tool(
    name: str, tool_input: dict, ui_from: int | None, ui_to: int | None, sources: list[dict]
) -> dict:
    from_num, to_num = _clamp_range(
        tool_input.get("date_from"), tool_input.get("date_to"), ui_from, ui_to
    )
    if name == "search_messages":
        query = (tool_input.get("query") or "").strip()
        if not query:
            raise ToolInputError("query is required")
        result = _search_messages(query, from_num, to_num)
        for item in result["results"]:
            label = item["source"] + (f" ({item['date']})" if item["date"] else "")
            if not any(src["label"] == label for src in sources):
                sources.append({"label": label, "source": item["source"]})
        return result
    if name == "count_messages":
        keywords = tool_input.get("keywords") or []
        if not isinstance(keywords, list):
            raise ToolInputError("keywords must be an array of strings")
        match = tool_input.get("match") or "all"
        if match not in ("all", "any"):
            raise ToolInputError("match must be 'all' or 'any'")
        return _count_messages(from_num, to_num, [str(k) for k in keywords], match)
    raise ToolInputError(f"unknown tool: {name}")


def _answer_query(
    query: str, ui_from: int | None, ui_to: int | None
) -> tuple[str, list[dict], bool]:
    """Run the guardrailed converse tool loop.

    Returns (answer, sources, guardrail_intervened)."""
    user_text = query
    if ui_from is not None or ui_to is not None:
        user_text += (
            f"\n\n[The user has an active date filter: "
            f"{_day_str(ui_from) or 'beginning'} to {_day_str(ui_to) or 'today'}. "
            "All tool results are already restricted to this range.]"
        )

    messages: list[dict] = [{"role": "user", "content": [{"text": user_text}]}]
    sources: list[dict] = []

    converse_kwargs: dict = {
        "modelId": GEN_MODEL_ID,
        "system": [{"text": SYSTEM_PROMPT}],
        "toolConfig": TOOL_CONFIG,
        "inferenceConfig": {"maxTokens": 2048},
    }
    if GUARDRAIL_ID:
        converse_kwargs["guardrailConfig"] = {
            "guardrailIdentifier": GUARDRAIL_ID,
            "guardrailVersion": GUARDRAIL_VERSION,
        }

    answer = ""
    for turn in range(MAX_TOOL_TURNS):
        response = bedrock_runtime.converse(messages=messages, **converse_kwargs)
        stop_reason = response.get("stopReason")
        output_message = response.get("output", {}).get("message", {})
        content = output_message.get("content", [])
        answer = next((block["text"] for block in content if "text" in block), answer)

        if stop_reason == "guardrail_intervened":
            logger.warning("Guardrail %s v%s intervened", GUARDRAIL_ID, GUARDRAIL_VERSION)
            return answer or "Response blocked by content policy.", [], True

        if stop_reason != "tool_use":
            logger.info("Tool loop done after %d turn(s), stopReason=%s", turn + 1, stop_reason)
            return answer, sources, False

        messages.append(output_message)
        tool_results = []
        for block in content:
            tool_use = block.get("toolUse")
            if not tool_use:
                continue
            name = tool_use.get("name", "")
            tool_input = tool_use.get("input") or {}
            logger.info("Tool call %d: %s(%s)", turn + 1, name, json.dumps(tool_input))
            try:
                result = _execute_tool(name, tool_input, ui_from, ui_to, sources)
                tool_results.append({"toolResult": {
                    "toolUseId": tool_use["toolUseId"],
                    "content": [{"json": result}],
                }})
            except ToolInputError as exc:
                tool_results.append({"toolResult": {
                    "toolUseId": tool_use["toolUseId"],
                    "content": [{"text": str(exc)}],
                    "status": "error",
                }})
        messages.append({"role": "user", "content": tool_results})

    logger.warning("Tool loop hit MAX_TOOL_TURNS=%d without a final answer", MAX_TOOL_TURNS)
    return (
        answer or "The question could not be answered within the allowed number of steps.",
        sources,
        False,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/query")
def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    try:
        from_num = _parse_day(req.date_from) if req.date_from else None
        to_num = _parse_day(req.date_to) if req.date_to else None
    except ToolInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if from_num is not None and to_num is not None and from_num > to_num:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")

    try:
        answer, sources, guardrail_intervened = _answer_query(req.query, from_num, to_num)
    except (ClientError, BotoCoreError) as exc:
        logger.error("Query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Query failed: {exc}")

    if guardrail_intervened:
        # Don't cite sources under a blocked/masked answer
        return {"answer": answer, "sources": []}
    return {
        "answer": answer,
        "sources": [
            {"label": src["label"], "url": _source_url(src["source"])} for src in sources
        ],
    }


# SPA static files — registered last so API routes take precedence
if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        return FileResponse(str(STATIC_DIR / "index.html"))
