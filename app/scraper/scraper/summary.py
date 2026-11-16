"""Collection summary documents for the Bedrock Knowledge Base.

A vector search only sees the few chunks it retrieves, so it cannot answer
"how many CSMS messages are there?" — the model would count what it was shown.
This module pre-computes those answers. It reads every message the scraper has
stored, counts them by sent date, by country mentioned and by attachments, and
writes the results as a few small Markdown documents (each with a
.metadata.json sidecar) under their own prefix, where a dedicated Knowledge
Base indexes them:

    <SUMMARY_PREFIX>csms-summary-overview.md     totals, per year, top countries, latest messages
    <SUMMARY_PREFIX>csms-summary-year-2026.md    one per year: per month, countries that year
    <SUMMARY_PREFIX>csms-summary-countries.md    every country, all years

Rules the documents follow:
  * Every number is computed here; nothing asks a model to count.
  * Each document is one self-contained chunk (the Knowledge Base data source
    uses NONE chunking), so it says what it covers and when it was computed,
    and stays under MAX_DOC_CHARS.
  * Topic counts ("how many messages about X") are not pre-computed, and the
    overview says so, so that an answer states this instead of guessing.

The summary is rebuilt from scratch from what is stored (S3, or the --dry-run
output directory): like the rest of the scraper it keeps no local state.
"""

import calendar
import json
import logging
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from .config import Settings
from .countries import detect_countries
from .kb_index import SIDECAR_SUFFIX
from .kb_metadata import SIDECAR_MAX_BYTES, sidecar_payload
from .textdoc import split_text_doc

logger = logging.getLogger(__name__)

DEFAULT_SUMMARY_DIR = "csms-summary/"   # --dry-run only; real runs need SUMMARY_PREFIX
DOC_NAME_PREFIX = "csms-summary-"
# One document = one chunk = one embedding. 12,000 characters of tables is about
# 4-5k tokens: inside the embedding model's input limit (Titan Text v2: 8,192
# tokens) and S3 Vectors' per-vector metadata limit, which holds the chunk text.
MAX_DOC_CHARS = 12_000
TOP_COUNTRIES = 20
RECENT_MESSAGES = 10

_READ_WORKERS = 16
_SUBJECT_DISPLAY_MAX = 160
_MESSAGE_DOC_RE = re.compile(r"^(?P<mid>[^/]+)/csms-(?P=mid)\.txt$")
_ATTACHMENT_RE = re.compile(r"^(?P<mid>[^/]+)/attachments/[^/]+$")
_GENERATED_NAME_RE = re.compile(rf"^{DOC_NAME_PREFIX}[a-z0-9-]+\.md(\.metadata\.json)?$")
_INGESTION_RUNNING = {"STARTING", "IN_PROGRESS"}


# ----------------------------------------------------------------------
# Where the stored messages are read from and the summary is written to
# ----------------------------------------------------------------------

class S3Store:
    """Objects in one bucket, addressed by key."""

    def __init__(self, bucket: str, client=None):
        if not bucket:
            raise SystemExit(
                "S3_BUCKET_NAME is not set. Export it (or put it in .env.local for "
                "docker compose), or use --dry-run to build the summary from local files."
            )
        if client is None:
            import boto3  # deferred so --dry-run works without boto3/credentials
            from botocore.config import Config

            client = boto3.client("s3", config=Config(max_pool_connections=_READ_WORKERS * 2))
        self._s3 = client
        self._bucket = bucket

    def describe(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def read(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def write(self, key: str, body: bytes, content_type: str) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType=content_type)

    def delete(self, keys: list[str]) -> None:
        for start in range(0, len(keys), 1000):   # DeleteObjects limit
            response = self._s3.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": k} for k in keys[start:start + 1000]], "Quiet": True},
            )
            if response.get("Errors"):
                raise RuntimeError(f"Could not delete stale summary objects: {response['Errors'][:5]}")


class LocalStore:
    """Files under one directory (the --dry-run output), addressed by relative path."""

    def __init__(self, root: str):
        self._root = root

    def _path(self, key: str) -> str:
        return os.path.join(self._root, *key.split("/"))

    def describe(self, key: str) -> str:
        return self._path(key)

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        for dirpath, _, filenames in os.walk(self._root):
            for name in filenames:
                key = os.path.relpath(os.path.join(dirpath, name), self._root).replace(os.sep, "/")
                if key.startswith(prefix):
                    keys.append(key)
        return sorted(keys)

    def read(self, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            return f.read()

    def write(self, key: str, body: bytes, content_type: str) -> None:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(body)

    def delete(self, keys: list[str]) -> None:
        for key in keys:
            os.remove(self._path(key))


# ----------------------------------------------------------------------
# Reading the stored messages
# ----------------------------------------------------------------------

@dataclass
class MessageRecord:
    message_id: str
    subject: str
    sent_date: date | None      # UTC date from the sidecar; None => undated
    timestamp: int | None       # Unix seconds from the sidecar, orders same-day messages
    countries: list[str]
    attachments: int            # attachment files stored for this message


def _sidecar_attributes(store, key: str) -> dict:
    try:
        attributes = json.loads(store.read(key)).get("metadataAttributes", {})
    except (ValueError, AttributeError):
        attributes = None
    if not isinstance(attributes, dict):
        logger.warning("Unreadable sidecar %s — its message is counted as undated", store.describe(key))
        return {}
    return attributes


def _sent(attributes: dict) -> tuple[date | None, int | None]:
    day: date | None = None
    raw = attributes.get("sent_date")
    if isinstance(raw, str):
        try:
            day = date.fromisoformat(raw)
        except ValueError:
            day = None
    if day is None and attributes.get("date_numeric") is not None:
        try:
            day = datetime.strptime(str(int(attributes["date_numeric"])), "%Y%m%d").date()
        except (ValueError, TypeError):
            day = None
    timestamp = attributes.get("timestamp")
    return day, int(timestamp) if isinstance(timestamp, (int, float)) else None


def load_messages(store, prefix: str) -> list[MessageRecord]:
    """One record per complete message under `prefix`.

    A message is complete when its main text document exists (the pipeline
    uploads it last). Dates come from the sidecar. Countries are detected again
    from the stored text rather than read from the sidecar, whose
    `related_countries` list is trimmed to fit the 1 KB sidecar limit.
    """
    keys = store.list_keys(prefix)
    key_set = set(keys)
    attachments: Counter = Counter()
    message_ids: list[str] = []
    for key in keys:
        if key.endswith(SIDECAR_SUFFIX):
            continue
        relative = key[len(prefix):]
        match = _MESSAGE_DOC_RE.match(relative)
        if match:
            message_ids.append(match["mid"])
            continue
        match = _ATTACHMENT_RE.match(relative)
        if match:
            attachments[match["mid"]] += 1

    def load(message_id: str) -> MessageRecord:
        doc_key = f"{prefix}{message_id}/csms-{message_id}.txt"
        subject, body = split_text_doc(store.read(doc_key).decode("utf-8", errors="replace"))
        sidecar_key = f"{doc_key}{SIDECAR_SUFFIX}"
        if sidecar_key in key_set:
            attributes = _sidecar_attributes(store, sidecar_key)
        else:
            logger.warning("No sidecar for %s — counted as undated", store.describe(doc_key))
            attributes = {}
        sent_date, timestamp = _sent(attributes)
        return MessageRecord(
            message_id=message_id,
            subject=subject or str(attributes.get("subject", "")),
            sent_date=sent_date,
            timestamp=timestamp,
            countries=detect_countries(subject, body),
            attachments=attachments[message_id],
        )

    logger.info("Reading %d stored message(s) under %s", len(message_ids), store.describe(prefix))
    with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
        return list(pool.map(load, sorted(message_ids)))


# ----------------------------------------------------------------------
# Counting
# ----------------------------------------------------------------------

@dataclass
class Tally:
    messages: int = 0
    with_attachments: int = 0
    attachment_files: int = 0

    def add(self, record: MessageRecord) -> None:
        self.messages += 1
        if record.attachments:
            self.with_attachments += 1
            self.attachment_files += record.attachments


@dataclass
class CollectionStats:
    generated: date
    total: Tally = field(default_factory=Tally)
    undated: int = 0
    with_countries: int = 0
    by_year: dict[int, Tally] = field(default_factory=dict)
    by_month: dict[tuple[int, int], Tally] = field(default_factory=dict)
    countries: Counter = field(default_factory=Counter)
    countries_by_year: dict[int, Counter] = field(default_factory=dict)
    dated: list[MessageRecord] = field(default_factory=list)   # oldest first

    @property
    def earliest(self) -> MessageRecord | None:
        return self.dated[0] if self.dated else None

    @property
    def latest(self) -> MessageRecord | None:
        return self.dated[-1] if self.dated else None

    def year_span(self, year: int) -> tuple[date, date]:
        days = [r.sent_date for r in self.dated if r.sent_date.year == year]
        return days[0], days[-1]


def compute_stats(records: list[MessageRecord], generated: date) -> CollectionStats:
    stats = CollectionStats(generated=generated)
    for record in records:
        stats.total.add(record)
        mentioned = set(record.countries)
        if mentioned:
            stats.with_countries += 1
            stats.countries.update(mentioned)
        if record.sent_date is None:
            stats.undated += 1
            continue
        year, month = record.sent_date.year, record.sent_date.month
        stats.by_year.setdefault(year, Tally()).add(record)
        stats.by_month.setdefault((year, month), Tally()).add(record)
        stats.countries_by_year.setdefault(year, Counter()).update(mentioned)
        stats.dated.append(record)
    stats.dated.sort(key=lambda r: (r.sent_date, r.timestamp or 0, r.message_id))
    return stats


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------

@dataclass
class SummaryDoc:
    filename: str
    text: str
    attributes: dict   # sidecar metadataAttributes


def _n(value: int) -> str:
    return f"{value:,}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _short(subject: str) -> str:
    return subject if len(subject) <= _SUBJECT_DISPLAY_MAX else subject[:_SUBJECT_DISPLAY_MAX - 1].rstrip() + "…"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def _tally_row(label: str, tally: Tally) -> list[str]:
    return [label, _n(tally.messages), _n(tally.with_attachments), _n(tally.attachment_files)]


def _country_rows(counts: Counter, limit: int | None = None) -> list[list[str]]:
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [[name, _n(count)] for name, count in ranked[:limit]]


def _scope(stats: CollectionStats) -> str:
    return (
        f"All numbers are exact counts computed on {stats.generated.isoformat()} (UTC) from the CSMS "
        "messages held in this assistant's collection. They cover only this collection, which can hold "
        "fewer messages than CBP has published. Sent dates are UTC dates."
    )


def _describe(record: MessageRecord) -> str:
    return f"CSMS # {record.message_id}, sent {record.sent_date.isoformat()}: {_short(record.subject)}"


_TALLY_HEADER = ["Messages", "Messages with attachments", "Attachment files"]
_NOT_TRACKED = "Mentions of the United States are not counted."
_COUNTRIES_OVERLAP = (
    "One message can mention several countries or regions, so these counts overlap: counts for two or "
    "more countries cannot be added together, and the number of messages that mention one country or "
    "another is not available."
)


def _overview(stats: CollectionStats) -> SummaryDoc:
    total = stats.total
    lines = [
        "# CSMS message collection: overall statistics",
        "",
        (
            "This document gives the overall statistics for the collection of U.S. Customs and Border "
            "Protection (CBP) Cargo Systems Messaging Service (CSMS) messages held by this assistant: how "
            "many CSMS messages there are in total and per year, how many have attachments, which sent "
            "dates the collection covers, which countries are mentioned most often, and which messages "
            "are the most recent."
        ),
        "",
        _scope(stats),
        "",
        "## Totals",
        "",
        f"- Total CSMS messages in the collection: {_n(total.messages)}",
    ]
    if stats.dated:
        lines += [
            f"- Sent dates covered: {stats.earliest.sent_date.isoformat()} to {stats.latest.sent_date.isoformat()}",
            f"- Earliest message: {_describe(stats.earliest)}",
            f"- Latest message: {_describe(stats.latest)}",
        ]
    lines += [
        f"- Messages with at least one attachment: {_n(total.with_attachments)}",
        f"- Messages without attachments: {_n(total.messages - total.with_attachments)}",
        f"- Attachment files in total: {_n(total.attachment_files)}",
        (
            "- Messages that mention at least one country or region other than the United States: "
            f"{_n(stats.with_countries)}"
        ),
    ]
    if stats.undated:
        lines.append(
            f"- Messages with no recorded sent date: {_n(stats.undated)} "
            "(counted in the totals above, but in no year or month)"
        )

    if stats.by_year:
        lines += ["", "## CSMS messages per year", ""]
        lines += _table(
            ["Year", *_TALLY_HEADER],
            [_tally_row(str(year), stats.by_year[year]) for year in sorted(stats.by_year)],
        )
        lines += [
            "",
            (
                "Years that are not listed have no messages in this collection. Counts per month, and per "
                "country for one year, are in the statistics document for that year."
            ),
        ]

    if stats.countries:
        lines += ["", "## Countries and regions mentioned most often (all years)", ""]
        lines += _table(["Country or region", "Messages mentioning it"], _country_rows(stats.countries, TOP_COUNTRIES))
        lines += [
            "",
            f"The complete list is in the statistics document for countries. {_COUNTRIES_OVERLAP} {_NOT_TRACKED}",
        ]

    if stats.dated:
        recent = stats.dated[::-1][:RECENT_MESSAGES]
        lines += ["", f"## The {len(recent)} most recent messages", ""]
        lines += _table(
            ["Sent", "CSMS #", "Subject"],
            [[r.sent_date.isoformat(), r.message_id, _short(r.subject)] for r in recent],
        )

    lines += [
        "",
        "## What these statistics do not cover",
        "",
        (
            "They count messages by sent date, by country or region mentioned, and by attachments. They do "
            "not count messages by topic or subject matter (for example ACE outages or a particular tariff "
            'action), so a question such as "how many messages are about X" cannot be answered from them.'
        ),
    ]
    return SummaryDoc(
        filename=f"{DOC_NAME_PREFIX}overview.md",
        text="\n".join(lines) + "\n",
        attributes={"summary_kind": "overview", "message_count": total.messages},
    )


def _year(stats: CollectionStats, year: int) -> SummaryDoc:
    tally = stats.by_year[year]
    first, last = stats.year_span(year)
    months = [m for (y, m) in sorted(stats.by_month) if y == year]
    lines = [
        f"# CSMS message statistics for {year}",
        "",
        (
            "This document gives the statistics for CBP Cargo Systems Messaging Service (CSMS) messages sent "
            f"in {year}: how many messages were sent in the year and in each month, how many had attachments, "
            f"and which countries or regions the {year} messages mention."
        ),
        "",
        _scope(stats),
        "",
        f"## Totals for {year}",
        "",
        f"- CSMS messages sent in {year}: {_n(tally.messages)}",
        f"- Sent dates covered in {year}: {first.isoformat()} to {last.isoformat()}",
        f"- Messages sent in {year} with at least one attachment: {_n(tally.with_attachments)}",
        f"- Attachment files on {year} messages: {_n(tally.attachment_files)}",
        "",
        f"## CSMS messages per month in {year}",
        "",
    ]
    lines += _table(
        ["Month", *_TALLY_HEADER],
        [
            _tally_row(f"{calendar.month_name[m]} {year} ({year}-{m:02d})", stats.by_month[(year, m)])
            for m in months
        ],
    )
    lines += ["", f"Months of {year} that are not listed have no messages in this collection."]

    counts = stats.countries_by_year.get(year)
    lines += ["", f"## Countries and regions mentioned in {year} messages", ""]
    if counts:
        lines += _table(["Country or region", f"{year} messages mentioning it"], _country_rows(counts))
        lines += [
            "",
            (
                f"These are counts for the whole of {year}: how many messages mention a country within a single "
                f"month is not available. {_COUNTRIES_OVERLAP} Countries and regions that are not listed are "
                f"mentioned in no {year} message in this collection. {_NOT_TRACKED}"
            ),
        ]
    else:
        lines.append(f"No {year} message in this collection mentions a country or region. {_NOT_TRACKED}")
    return SummaryDoc(
        filename=f"{DOC_NAME_PREFIX}year-{year}.md",
        text="\n".join(lines) + "\n",
        attributes={"summary_kind": "year", "year": year, "message_count": tally.messages},
    )


def _countries(stats: CollectionStats) -> SummaryDoc:
    lines = [
        "# CSMS message statistics by country or region",
        "",
        (
            "This document gives, for every country or region, how many CBP Cargo Systems Messaging Service "
            "(CSMS) messages in this assistant's collection mention it, across all years."
        ),
        "",
        _scope(stats),
        "",
        f"- Countries and regions mentioned: {_n(len(stats.countries))}",
        f"- Messages that mention at least one of them: {_n(stats.with_countries)} of {_n(stats.total.messages)}",
        "",
    ]
    if stats.countries:
        lines += _table(["Country or region", "Messages mentioning it"], _country_rows(stats.countries))
        lines.append("")
    lines.append(
        "A message is counted once for each country or region named in its subject or body text. "
        f"{_COUNTRIES_OVERLAP} {_NOT_TRACKED} Georgia is not counted either, because the name collides "
        "with the U.S. state. Countries and regions that are not listed are mentioned in no message in "
        "this collection. Counts for a single year are in the statistics document for that year."
    )
    return SummaryDoc(
        filename=f"{DOC_NAME_PREFIX}countries.md",
        text="\n".join(lines) + "\n",
        attributes={"summary_kind": "countries", "message_count": stats.total.messages},
    )


def build_documents(stats: CollectionStats) -> list[SummaryDoc]:
    docs = [_overview(stats), *(_year(stats, year) for year in sorted(stats.by_year)), _countries(stats)]
    for doc in docs:
        doc.attributes = {
            "doc_type": "csms_summary",
            "generated_date": stats.generated.isoformat(),
            **doc.attributes,
        }
        if len(doc.text) > MAX_DOC_CHARS:
            raise ValueError(
                f"{doc.filename} is {len(doc.text)} characters (limit {MAX_DOC_CHARS}): it must stay a "
                "single Knowledge Base chunk — split it into more documents in summary.py"
            )
    return docs


# ----------------------------------------------------------------------
# Writing + Knowledge Base sync
# ----------------------------------------------------------------------

def publish(store, summary_prefix: str, docs: list[SummaryDoc]) -> int:
    """Write every document (sidecar first, like the pipeline) and remove
    generated documents from earlier runs that are no longer produced.
    Returns the number of stale objects removed."""
    wanted: set[str] = set()
    for doc in docs:
        key = f"{summary_prefix}{doc.filename}"
        payload = sidecar_payload(doc.attributes)
        if len(payload) > SIDECAR_MAX_BYTES:
            raise ValueError(f"Sidecar for {doc.filename} is {len(payload)} B (limit {SIDECAR_MAX_BYTES})")
        store.write(f"{key}{SIDECAR_SUFFIX}", payload, "application/json")
        store.write(key, doc.text.encode("utf-8"), "text/markdown; charset=utf-8")
        wanted.update((key, f"{key}{SIDECAR_SUFFIX}"))
        logger.info("Wrote %s (%d characters)", store.describe(key), len(doc.text))

    stale = [
        key for key in store.list_keys(summary_prefix)
        if key not in wanted and _GENERATED_NAME_RE.match(key[len(summary_prefix):])
    ]
    if stale:
        logger.info("Removing %d stale summary object(s): %s", len(stale), ", ".join(stale))
        store.delete(stale)
    return len(stale)


def sync_knowledge_base(
    knowledge_base_id: str,
    data_source_id: str,
    client=None,
    timeout: float = 900.0,
    poll_seconds: float = 5.0,
) -> dict:
    """Run an ingestion job on the summary data source and wait for it.
    Returns the job statistics."""
    if client is None:
        import boto3

        client = boto3.client("bedrock-agent")
    ids = {"knowledgeBaseId": knowledge_base_id, "dataSourceId": data_source_id}
    deadline = time.monotonic() + timeout

    while True:
        try:
            job = client.start_ingestion_job(description="CSMS collection summary refresh", **ids)["ingestionJob"]
            break
        except client.exceptions.ConflictException:
            # One job per data source at a time; a job that started before the
            # upload may have missed the new documents, so wait and run our own.
            if time.monotonic() > deadline:
                raise TimeoutError(f"Another ingestion job was still running after {timeout:.0f}s") from None
            logger.info("An ingestion job is already running on data source %s — waiting", data_source_id)
            time.sleep(poll_seconds)

    job_id = job["ingestionJobId"]
    logger.info("Started ingestion job %s on knowledge base %s", job_id, knowledge_base_id)
    while job["status"] in _INGESTION_RUNNING:
        if time.monotonic() > deadline:
            raise TimeoutError(f"Ingestion job {job_id} still {job['status']} after {timeout:.0f}s")
        time.sleep(poll_seconds)
        job = client.get_ingestion_job(ingestionJobId=job_id, **ids)["ingestionJob"]

    statistics = job.get("statistics", {})
    reasons = "; ".join(job.get("failureReasons", []))
    if job["status"] != "COMPLETE":
        raise RuntimeError(f"Ingestion job {job_id} ended {job['status']}: {reasons}")
    if statistics.get("numberOfDocumentsFailed"):
        raise RuntimeError(
            f"Ingestion job {job_id} failed on {statistics['numberOfDocumentsFailed']} document(s): {reasons}"
        )
    logger.info("Ingestion job %s complete: %s", job_id, statistics)
    return statistics


def check_prefixes(message_prefix: str, summary_prefix: str) -> None:
    """The summary documents must never land where the message Knowledge Base
    (or the scraper's own message listing) would pick them up."""
    if not summary_prefix:
        raise SystemExit(
            "SUMMARY_PREFIX is not set. Set it to the summary Knowledge Base's source prefix "
            "(the stack's ScraperEnv output has it), or use --dry-run."
        )
    if not message_prefix or message_prefix.startswith(summary_prefix) or summary_prefix.startswith(message_prefix):
        raise SystemExit(
            f"SUMMARY_PREFIX ({summary_prefix!r}) and S3_PREFIX ({message_prefix!r}) overlap. The summary "
            "needs its own prefix, outside the messages', so each Knowledge Base indexes only its own documents."
        )


@dataclass
class SummaryResult:
    messages: int = 0
    documents: int = 0
    removed: int = 0
    synced: bool = False

    def summary(self) -> str:
        return (
            f"messages={self.messages} documents={self.documents} "
            f"removed={self.removed} kb_synced={'yes' if self.synced else 'no'}"
        )


def refresh_summary(
    settings: Settings,
    dry_run: bool = False,
    output_dir: str = "out",
    sync: bool = True,
    generated: date | None = None,
) -> SummaryResult:
    """Rebuild the summary documents from every stored message.

    dry_run: read the message files kept in `output_dir` by --dry-run scrapes
    and write the summary next to them; no AWS.
    """
    if dry_run:
        store = LocalStore(output_dir)
        message_prefix = ""
        summary_prefix = settings.summary_prefix or DEFAULT_SUMMARY_DIR
    else:
        check_prefixes(settings.s3_prefix, settings.summary_prefix)
        store = S3Store(settings.s3_bucket)
        message_prefix, summary_prefix = settings.s3_prefix, settings.summary_prefix

    records = load_messages(store, message_prefix)
    if not records:
        # Never replace a good summary with "0 messages" because of a wrong prefix.
        logger.warning(
            "No stored CSMS messages found under %s — summary left unchanged", store.describe(message_prefix)
        )
        return SummaryResult()

    stats = compute_stats(records, generated or datetime.now(timezone.utc).date())
    docs = build_documents(stats)
    removed = publish(store, summary_prefix, docs)
    result = SummaryResult(messages=len(records), documents=len(docs), removed=removed)
    logger.info(
        "Summary of %d message(s) written as %d document(s) under %s",
        result.messages, result.documents, store.describe(summary_prefix),
    )

    if dry_run or not sync:
        return result
    if settings.summary_knowledge_base_id and settings.summary_kb_data_source_id:
        sync_knowledge_base(settings.summary_knowledge_base_id, settings.summary_kb_data_source_id)
        result.synced = True
    else:
        logger.info(
            "SUMMARY_KNOWLEDGE_BASE_ID / SUMMARY_KB_DATA_SOURCE_ID are not set — sync the summary "
            "Knowledge Base's data source to index the new documents"
        )
    return result
