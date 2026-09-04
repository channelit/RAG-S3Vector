"""Re-index documents in the Bedrock Knowledge Base via the direct document APIs.

For each source document the KB holds, a re-index is:

    DeleteKnowledgeBaseDocuments  -> drops the document's current vectors
    IngestKnowledgeBaseDocuments  -> re-embeds the S3 object with its
                                     `.metadata.json` sidecar attached as the
                                     document metadata

so the new vectors carry the sidecar attributes (`date_numeric`, `sent_date`,
`message_id`, ...) that the container backend's date filter relies on. Both
APIs accept at most 10 documents per call and complete asynchronously, so each
batch is polled with GetKnowledgeBaseDocuments until it settles before the
next step runs.

Documents whose sidecar carries no `date_numeric` are reported and skipped:
re-indexing can't add a date the scraper never found — re-scrape them with
`--force` instead.
"""

import json
import logging
import time
from dataclasses import dataclass, field

from .config import Settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 10                      # API limit for delete/ingest
SIDECAR_SUFFIX = ".metadata.json"

_DELETE_PENDING = {"DELETING", "DELETE_IN_PROGRESS"}
_INGEST_PENDING = {"STARTING", "PENDING", "IN_PROGRESS"}


@dataclass
class KBDocument:
    uri: str                         # s3://bucket/key of the source document
    sidecar_uri: str                 # s3://bucket/key.metadata.json
    message_id: str | None = None
    date_numeric: int | None = None  # from the sidecar; None => undated

    def describe(self) -> str:
        return self.uri.rsplit("/", 2)[-1] if self.message_id is None else f"CSMS {self.message_id} {self.uri.rsplit('/', 1)[-1]}"


@dataclass
class ReindexStats:
    reindexed: int = 0
    failed: int = 0
    undated: int = 0
    failures: list[str] = field(default_factory=list)
    undated_docs: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return f"reindexed={self.reindexed} failed={self.failed} undated={self.undated}"


def _s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"


def _identifier(uri: str) -> dict:
    return {"dataSourceType": "S3", "s3": {"uri": uri}}


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


class KBIndexer:
    def __init__(self, settings: Settings, s3_client=None, agent_client=None, poll_seconds: float = 3.0):
        if not settings.knowledge_base_id or not settings.kb_data_source_id:
            raise SystemExit(
                "KNOWLEDGE_BASE_ID and KB_DATA_SOURCE_ID must be set to re-index "
                "(Console → Bedrock → Knowledge Bases → your KB → Data sources)."
            )
        if not settings.s3_bucket:
            raise SystemExit("S3_BUCKET_NAME is not set.")
        if s3_client is None or agent_client is None:
            import boto3  # deferred so unit tests / --dry-run scrape don't need it

            s3_client = s3_client or boto3.client("s3")
            agent_client = agent_client or boto3.client("bedrock-agent")
        self._s3 = s3_client
        self._agent = agent_client
        self._bucket = settings.s3_bucket
        self._prefix = settings.s3_prefix
        self._kb_id = settings.knowledge_base_id
        self._ds_id = settings.kb_data_source_id
        self._poll = poll_seconds

    # ------------------------------------------------------------------
    # Discovery from S3
    # ------------------------------------------------------------------

    def discover(
        self, message_ids: list[str] | None = None, limit: int | None = None
    ) -> tuple[list[KBDocument], list[str]]:
        """Every document under the bucket prefix that has a sidecar, with the
        sidecar's date_numeric resolved. Returns (documents, keys_without_sidecar).
        `message_ids` restricts discovery to those messages' prefixes."""
        wanted = {m.strip() for m in message_ids} if message_ids else None
        keys: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))

        sidecars = {k for k in keys if k.endswith(SIDECAR_SUFFIX)}
        docs: list[KBDocument] = []
        no_sidecar: list[str] = []
        for key in sorted(keys):
            if key in sidecars or key.endswith("/"):
                continue
            message_id = key[len(self._prefix):].split("/", 1)[0] or None
            if wanted is not None and message_id not in wanted:
                continue
            if f"{key}{SIDECAR_SUFFIX}" not in sidecars:
                no_sidecar.append(key)
                continue
            docs.append(
                KBDocument(
                    uri=_s3_uri(self._bucket, key),
                    sidecar_uri=_s3_uri(self._bucket, f"{key}{SIDECAR_SUFFIX}"),
                    message_id=message_id,
                )
            )
        if limit is not None:
            docs = docs[:limit]
        for doc in docs:
            doc.date_numeric = self._sidecar_date(doc)
        logger.info(
            "Discovered %d document(s) with sidecars under s3://%s/%s (%d without a sidecar)",
            len(docs), self._bucket, self._prefix, len(no_sidecar),
        )
        return docs, no_sidecar

    def _sidecar_date(self, doc: KBDocument) -> int | None:
        key = doc.sidecar_uri.split("/", 3)[3]
        body = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        try:
            value = json.loads(body).get("metadataAttributes", {}).get("date_numeric")
            return int(value) if value is not None else None
        except (ValueError, AttributeError, TypeError):
            logger.warning("Unreadable sidecar %s", doc.sidecar_uri)
            return None

    # ------------------------------------------------------------------
    # Delete + ingest
    # ------------------------------------------------------------------

    def reindex(self, docs: list[KBDocument], timeout: float = 900.0) -> ReindexStats:
        """Delete then re-ingest each document (batches of 10), waiting for
        every batch to settle. Undated documents are skipped, not re-indexed."""
        stats = ReindexStats()
        dated: list[KBDocument] = []
        for doc in docs:
            if doc.date_numeric is None:
                stats.undated += 1
                stats.undated_docs.append(doc.uri)
                logger.warning("Skipping %s — sidecar has no date_numeric (re-scrape with --force)", doc.uri)
            else:
                dated.append(doc)

        for batch in _chunks(dated, BATCH_SIZE):
            uris = [d.uri for d in batch]
            logger.info("Deleting vectors for %d document(s): %s", len(uris), ", ".join(d.describe() for d in batch))
            self._agent.delete_knowledge_base_documents(
                knowledgeBaseId=self._kb_id,
                dataSourceId=self._ds_id,
                documentIdentifiers=[_identifier(u) for u in uris],
            )
            self._wait(uris, _DELETE_PENDING, timeout)

            logger.info("Ingesting %d document(s) with sidecar metadata", len(uris))
            self._agent.ingest_knowledge_base_documents(
                knowledgeBaseId=self._kb_id,
                dataSourceId=self._ds_id,
                documents=[
                    {
                        "content": {"dataSourceType": "S3", "s3": {"s3Location": {"uri": d.uri}}},
                        "metadata": {"type": "S3_LOCATION", "s3Location": {"uri": d.sidecar_uri}},
                    }
                    for d in batch
                ],
            )
            details = self._wait(uris, _INGEST_PENDING, timeout)
            for doc in batch:
                detail = details.get(doc.uri, {})
                status = detail.get("status", "UNKNOWN")
                if status == "INDEXED":
                    stats.reindexed += 1
                    logger.info("Re-indexed %s (date_numeric=%s)", doc.describe(), doc.date_numeric)
                else:
                    stats.failed += 1
                    reason = detail.get("statusReason", "")
                    stats.failures.append(f"{doc.uri}: {status} {reason}".strip())
                    logger.error("Re-index of %s ended %s %s", doc.uri, status, reason)

        logger.info("Re-index finished: %s", stats.summary())
        return stats

    def _wait(self, uris: list[str], pending: set[str], timeout: float) -> dict[str, dict]:
        """Poll GetKnowledgeBaseDocuments until no document is in a `pending`
        state. Documents the API no longer reports count as settled."""
        deadline = time.monotonic() + timeout
        while True:
            response = self._agent.get_knowledge_base_documents(
                knowledgeBaseId=self._kb_id,
                dataSourceId=self._ds_id,
                documentIdentifiers=[_identifier(u) for u in uris],
            )
            details = {
                d.get("identifier", {}).get("s3", {}).get("uri"): d
                for d in response.get("documentDetails", [])
            }
            still = [u for u in uris if details.get(u, {}).get("status") in pending]
            if not still:
                return details
            if time.monotonic() > deadline:
                raise TimeoutError(f"KB documents still {sorted(pending)} after {timeout:.0f}s: {still}")
            time.sleep(self._poll)
