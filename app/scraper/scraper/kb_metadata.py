"""Bedrock Knowledge Base metadata sidecars.

For a source document `X` in the KB's S3 data source, Bedrock reads
`X.metadata.json` from the same prefix:

    {"metadataAttributes": {"key": "string" | number | boolean | ["list"]}}

The file must stay under 10 KB. Numeric attributes (date_numeric, timestamp)
support range filtering in KB retrieval queries.
"""

import json
import logging
from datetime import timezone

from .bulletin import Bulletin

logger = logging.getLogger(__name__)

_SUBJECT_MAX = 1000
_SIDECAR_MAX_BYTES = 10 * 1024


def _date_fields(bulletin: Bulletin) -> dict:
    if bulletin.sent_at is None:
        return {}
    utc = bulletin.sent_at.astimezone(timezone.utc)
    return {
        "sent_date": utc.strftime("%Y-%m-%d"),
        "date_numeric": int(utc.strftime("%Y%m%d")),
        "timestamp": int(utc.timestamp()),
    }


def message_attributes(bulletin: Bulletin, countries: list[str]) -> dict:
    attrs = {
        "doc_type": "csms_message",
        "message_id": bulletin.message_id,
        "subject": bulletin.subject[:_SUBJECT_MAX],
        "source_url": bulletin.url,
        **_date_fields(bulletin),
    }
    if countries:
        attrs["related_countries"] = countries
    return attrs


def attachment_attributes(
    bulletin: Bulletin,
    countries: list[str],
    attachment_filename: str,
    attachment_url: str,
    attachment_index: int,
) -> dict:
    """Attachment docs carry their own identity plus the parent message's
    metadata (parent_* keys), so a PDF hit can always be traced back to —
    and filtered by — the CSMS message it was published under."""
    attrs = {
        "doc_type": "csms_attachment",
        "message_id": bulletin.message_id,
        "parent_message_id": bulletin.message_id,
        "parent_subject": bulletin.subject[:_SUBJECT_MAX],
        "parent_source_url": bulletin.url,
        "attachment_filename": attachment_filename,
        "attachment_url": attachment_url,
        "attachment_index": attachment_index,
        **_date_fields(bulletin),
    }
    if countries:
        attrs["related_countries"] = countries
    return attrs


def write_sidecar(document_path: str, attributes: dict) -> str:
    """Write `<document_path>.metadata.json` next to the document."""
    sidecar_path = f"{document_path}.metadata.json"
    payload = json.dumps({"metadataAttributes": attributes}, ensure_ascii=False, indent=2)
    if len(payload.encode("utf-8")) > _SIDECAR_MAX_BYTES:
        # Only free-text fields can realistically overflow — trim and retry.
        logger.warning("Sidecar over 10KB for %s — trimming text fields", document_path)
        for key in ("subject", "parent_subject"):
            if key in attributes:
                attributes[key] = attributes[key][:200]
        payload = json.dumps({"metadataAttributes": attributes}, ensure_ascii=False, indent=2)
    with open(sidecar_path, "w", encoding="utf-8") as f:
        f.write(payload)
    return sidecar_path
