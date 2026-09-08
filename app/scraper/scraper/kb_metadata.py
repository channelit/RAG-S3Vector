"""Bedrock Knowledge Base metadata sidecars.

For a source document `X` in the KB's S3 data source, Bedrock reads
`X.metadata.json` from the same prefix:

    {"metadataAttributes": {"key": "string" | number | boolean | ["list"]}}

The file must stay at or under 1 KB: the S3 Vectors-backed KB's sync job
silently *ignores* documents whose sidecar exceeds 1024 bytes (the 10 KB
figure applies to OpenSearch-backed stores). `fit_sidecar` enforces that.
Numeric attributes (date_numeric, timestamp) support range filtering in KB
retrieval queries.
"""

import json
import logging
from datetime import timezone

from .bulletin import Bulletin

logger = logging.getLogger(__name__)

_SUBJECT_MAX = 1000
SIDECAR_MAX_BYTES = 1024
_TRIMMED_SUBJECT_MAX = 200


def _date_fields(bulletin: Bulletin) -> dict:
    if bulletin.sent_at is None:
        logger.warning(
            "CSMS %s has no sent date — sidecar gets no date attributes, so the "
            "document will not match any date-range retrieval filter",
            bulletin.message_id,
        )
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


def sidecar_payload(attributes: dict) -> bytes:
    """Compact JSON — whitespace counts against the 1 KB limit."""
    return json.dumps(
        {"metadataAttributes": attributes}, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def fit_sidecar(attributes: dict, label: str = "") -> tuple[dict, bytes]:
    """Return (attributes, payload) guaranteed to be <= SIDECAR_MAX_BYTES.

    Trim order, least valuable first: drop countries from the end of
    `related_countries` (it is the only unbounded field — a Section 301/232
    message can name 40+ countries), then shorten subject fields, then drop
    `related_countries` altogether. Everything else is fixed-size identity/date
    data the UI depends on and is never touched.
    """
    attrs = dict(attributes)
    payload = sidecar_payload(attrs)
    if len(payload) <= SIDECAR_MAX_BYTES:
        return attrs, payload
    original = len(payload)

    countries = list(attrs.get("related_countries") or [])
    while countries and len(payload) > SIDECAR_MAX_BYTES:
        countries.pop()
        attrs["related_countries"] = countries
        payload = sidecar_payload(attrs)
    if len(payload) > SIDECAR_MAX_BYTES:
        for key in ("subject", "parent_subject"):
            if key in attrs:
                attrs[key] = attrs[key][:_TRIMMED_SUBJECT_MAX]
        payload = sidecar_payload(attrs)
    if len(payload) > SIDECAR_MAX_BYTES or not countries:
        attrs.pop("related_countries", None)
        payload = sidecar_payload(attrs)

    kept = len(attrs.get("related_countries") or [])
    logger.warning(
        "Sidecar %s was %d B (limit %d) — trimmed to %d B, related_countries %d -> %d",
        label, original, SIDECAR_MAX_BYTES, len(payload),
        len(attributes.get("related_countries") or []), kept,
    )
    return attrs, payload


def write_sidecar(document_path: str, attributes: dict) -> str:
    """Write `<document_path>.metadata.json` next to the document."""
    sidecar_path = f"{document_path}.metadata.json"
    _, payload = fit_sidecar(attributes, label=document_path)
    with open(sidecar_path, "wb") as f:
        f.write(payload)
    return sidecar_path
