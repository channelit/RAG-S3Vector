"""End-to-end processing of one CSMS message at a time:

    resolve ref -> skip if already in S3 -> fetch bulletin -> write text doc,
    download attachments, write .metadata.json sidecars -> upload each file to
    S3 (sidecar first, document second, main doc last) deleting each local
    file right after its upload -> remove the message's temp directory.

The main text document is uploaded last so its presence in S3 marks the
message complete; interrupted messages are retried on the next run.
"""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import date, timezone

from .bulletin import Bulletin, fetch_bulletin, parse_sent_datetime
from .config import Settings
from .countries import detect_countries
from .csms import MessageRef, bulletin_url_for_id, canonical_bulletin_url, id_from_bulletin_url, slugify
from .kb_metadata import attachment_attributes, message_attributes, write_sidecar
from .uploader import S3Uploader
from .web import WebClient

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    uploaded: int = 0
    skipped: int = 0
    filtered: int = 0
    not_found: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"uploaded={self.uploaded} skipped={self.skipped} filtered={self.filtered} "
            f"not_found={self.not_found} failed={self.failed}"
        )


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        client: WebClient,
        uploader: S3Uploader | None,   # None => dry run
        output_dir: str = "out",
        force: bool = False,
        since: date | None = None,
        until: date | None = None,
    ):
        self._settings = settings
        self._client = client
        self._uploader = uploader
        self._output_dir = output_dir
        self._force = force
        self._since = since
        self._until = until
        self._seen_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Ref resolution / cheap pre-checks
    # ------------------------------------------------------------------

    def _resolve(self, ref: MessageRef) -> MessageRef | None:
        """Turn a lnks.gd ref into a bulletin-URL ref; fill in computable fields."""
        if ref.lnks_url and not ref.url:
            resolved = self._client.resolve_lnks(ref.lnks_url)
            if not resolved:
                return None
            ref.url = canonical_bulletin_url(resolved)
            if not ref.url:
                logger.warning("lnks.gd %s resolved to non-bulletin URL %s", ref.lnks_url, resolved)
                return None
        if ref.url and not ref.message_id:
            ref.message_id = id_from_bulletin_url(ref.url)  # modern era only
        if ref.message_id and not ref.url:
            ref.url = bulletin_url_for_id(ref.message_id)
        return ref if ref.url else None

    def _date_in_range(self, day: date | None) -> bool:
        if day is None:
            return True  # unknown date — do not exclude
        if self._since and day < self._since:
            return False
        if self._until and day > self._until:
            return False
        return True

    def _hint_date(self, ref: MessageRef) -> date | None:
        if not ref.pub_date_hint:
            return None
        dt = parse_sent_datetime(ref.pub_date_hint)
        return dt.astimezone(timezone.utc).date() if dt else None

    # ------------------------------------------------------------------
    # Per-message processing
    # ------------------------------------------------------------------

    def process_ref(self, ref: MessageRef) -> str:
        """Returns one of: uploaded | skipped | filtered | not_found | failed."""
        try:
            resolved = self._resolve(ref)
        except Exception as exc:
            logger.error("Failed to resolve %s: %s", ref.describe(), exc)
            return "failed"
        if resolved is None:
            return "failed"
        ref = resolved

        if ref.message_id:
            if ref.message_id in self._seen_ids:
                return "skipped"
            if not self._date_in_range(self._hint_date(ref)):
                self._seen_ids.add(ref.message_id)
                return "filtered"
            if self._already_uploaded(ref.message_id):
                logger.info("CSMS %s already in S3 — skipping", ref.message_id)
                self._seen_ids.add(ref.message_id)
                return "skipped"

        try:
            bulletin = fetch_bulletin(self._client, ref.url)
        except Exception as exc:
            if "404" in str(exc):
                logger.warning("Bulletin not found (404): %s", ref.url)
                return "not_found"
            logger.error("Failed to fetch/parse %s: %s", ref.url, exc)
            return "failed"

        # The parsed page is authoritative for the ID (legacy bulletins).
        if bulletin.message_id in self._seen_ids:
            return "skipped"
        self._seen_ids.add(bulletin.message_id)

        sent_day = bulletin.sent_at.astimezone(timezone.utc).date() if bulletin.sent_at else None
        if not self._date_in_range(sent_day):
            logger.info("CSMS %s (%s) outside date range — filtered", bulletin.message_id, sent_day)
            return "filtered"

        if not self._force and self._already_uploaded(bulletin.message_id):
            logger.info("CSMS %s already in S3 — skipping", bulletin.message_id)
            return "skipped"

        try:
            self._package_and_ship(bulletin)
            return "uploaded"
        except Exception as exc:
            logger.error("Failed to package/upload CSMS %s: %s", bulletin.message_id, exc)
            return "failed"

    def _already_uploaded(self, message_id: str) -> bool:
        if self._force or self._uploader is None:
            return False
        return self._uploader.exists(self._uploader.message_doc_key(message_id))

    # ------------------------------------------------------------------
    # Packaging + upload
    # ------------------------------------------------------------------

    def _package_and_ship(self, bulletin: Bulletin) -> None:
        mid = bulletin.message_id
        if self._uploader is None:
            workdir = os.path.join(self._output_dir, mid)
            os.makedirs(workdir, exist_ok=True)
        else:
            workdir = tempfile.mkdtemp(prefix=f"csms-{mid}-")

        try:
            countries = detect_countries(bulletin.subject, bulletin.body_text)
            if countries:
                logger.info("CSMS %s related countries: %s", mid, countries)

            # (local_path, s3_key) pairs in upload order; each sidecar directly
            # before its document, main text document last (completion marker).
            uploads: list[tuple[str, str]] = []
            s3_prefix = f"{self._settings.s3_prefix}{mid}/"

            att_dir = os.path.join(workdir, "attachments")
            for idx, att in enumerate(bulletin.attachments):
                os.makedirs(att_dir, exist_ok=True)
                local_name = f"{idx + 1:02d}-{slugify(att.filename)}"
                local_path = os.path.join(att_dir, local_name)
                logger.info("Downloading attachment %d/%d: %s", idx + 1, len(bulletin.attachments), att.url)
                try:
                    size = self._client.download(att.url, local_path)
                except Exception as exc:
                    logger.error("Attachment download failed (%s): %s — continuing without it", att.url, exc)
                    continue
                logger.info("Attachment saved: %s (%d bytes)", local_name, size)
                sidecar = write_sidecar(
                    local_path,
                    attachment_attributes(bulletin, countries, att.filename, att.url, idx + 1),
                )
                key = f"{s3_prefix}attachments/{local_name}"
                uploads.append((sidecar, f"{key}.metadata.json"))
                uploads.append((local_path, key))

            doc_path = os.path.join(workdir, f"csms-{mid}.txt")
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(self._render_text_doc(bulletin))
            doc_sidecar = write_sidecar(doc_path, message_attributes(bulletin, countries))
            doc_key = f"{s3_prefix}csms-{mid}.txt"
            uploads.append((doc_sidecar, f"{doc_key}.metadata.json"))
            uploads.append((doc_path, doc_key))

            if self._uploader is None:
                logger.info("[dry-run] CSMS %s: %d file(s) kept in %s", mid, len(uploads), workdir)
                return

            for local_path, key in uploads:
                self._uploader.upload_and_delete(local_path, key)
            logger.info("CSMS %s complete: %d file(s) uploaded", mid, len(uploads))
        finally:
            if self._uploader is not None:
                shutil.rmtree(workdir, ignore_errors=True)

    @staticmethod
    def _render_text_doc(bulletin: Bulletin) -> str:
        lines = [
            f"CSMS # {bulletin.message_id} — {bulletin.subject}",
            f"Sent: {bulletin.sent_raw or 'unknown'}",
            f"Source: {bulletin.url}",
            "",
            bulletin.body_text or "(no body text)",
        ]
        if bulletin.attachments:
            lines += ["", "Attachments:"]
            lines += [f"- {att.filename}" for att in bulletin.attachments]
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Batch driver
    # ------------------------------------------------------------------

    def run(self, refs: list[MessageRef], limit: int | None = None) -> RunStats:
        stats = RunStats()
        total = len(refs)
        for i, ref in enumerate(refs):
            if limit is not None and stats.uploaded >= limit:
                logger.info("Reached limit of %d new message(s) — stopping", limit)
                break
            logger.info("[%d/%d] %s", i + 1, total, ref.describe())
            outcome = self.process_ref(ref)
            setattr(stats, outcome, getattr(stats, outcome) + 1)
            if outcome == "failed":
                stats.failures.append(ref.describe())
        logger.info("Run finished: %s", stats.summary())
        if stats.failures:
            logger.warning("Failed refs: %s", ", ".join(stats.failures[:20]))
        return stats
