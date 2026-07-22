"""CSMS identity helpers.

Facts (verified against live GovDelivery/CBP content, July 2026):
  * Modern message IDs (July 2019+) ARE GovDelivery bulletin IDs; the public
    bulletin URL encodes the ID in lowercase hex:
        CSMS # 69302472  ->  .../accounts/USDHSCBP/bulletins/42178c8
  * Legacy messages (1992–June 2019, IDs like "15-000970") were migrated to
    GovDelivery under unrelated bulletin IDs — their URLs can only be
    discovered (archive PDFs), not computed. Their pages keep the original
    "CSMS# 15-000970 - <subject>" title and original sent dateline.
"""

import re
import unicodedata
from dataclasses import dataclass, field

BULLETIN_URL_TEMPLATE = "https://content.govdelivery.com/accounts/USDHSCBP/bulletins/{code}"

# GovDelivery bulletin IDs below this are pre-"new CSMS" internal IDs (migrated
# legacy bulletins) whose decimal value is NOT the CSMS message number. The new
# numbering starts around 39.7M (July 2019); 35M is a safe dividing line.
MODERN_ID_FLOOR = 35_000_000

# ID is either legacy "YY-NNNNNN" or a plain number; the alternation order
# matters so the legacy form's internal dash is not mistaken for the
# id/subject separator (e.g. "CSMS# 15-000970 - Subject").
_SUBJECT_RE = re.compile(r"\s*CSMS\s*#?\s*(\d{2}-\d{6}|\d+)\s*[-–—:]\s*(.+)", re.IGNORECASE | re.DOTALL)

_PUBLIC_URL_RE = re.compile(
    r"content\.govdelivery\.com/(?:accounts/USDHSCBP/bulletins/|bulletins/gd/USDHSCBP-)([0-9a-fA-F]+)"
)
_ADMIN_URL_RE = re.compile(r"admin\.govdelivery\.com/accounts/USDHSCBP/bulletins/(\d+)")
_LNKS_URL_RE = re.compile(r"https?://lnks\.gd/\S+")


@dataclass
class MessageRef:
    """A pointer to one CSMS message, however it was discovered.

    Exactly one of (message_id, url, lnks_url) is enough to process it;
    subject/pub_date are optional hints from the discovery source.
    """
    message_id: str | None = None      # "69302472" or legacy "15-000970"
    url: str | None = None             # canonical public bulletin URL
    lnks_url: str | None = None        # unresolved lnks.gd short link
    subject_hint: str | None = None
    pub_date_hint: str | None = None

    def describe(self) -> str:
        return self.message_id or self.url or self.lnks_url or "(empty ref)"


def bulletin_url_for_id(message_id: int | str) -> str | None:
    """Compute the public bulletin URL for a modern numeric message ID."""
    try:
        numeric = int(str(message_id).strip())
    except ValueError:
        return None  # legacy "YY-NNNNNN" IDs cannot be computed
    return BULLETIN_URL_TEMPLATE.format(code=f"{numeric:x}")


def id_from_bulletin_url(url: str) -> str | None:
    """Extract the CSMS ID from a public bulletin URL — modern era only."""
    m = _PUBLIC_URL_RE.search(url)
    if not m:
        return None
    numeric = int(m.group(1), 16)
    return str(numeric) if numeric >= MODERN_ID_FLOOR else None


def canonical_bulletin_url(url: str) -> str | None:
    """Normalize any public bulletin URL form to the accounts/... canonical form."""
    m = _PUBLIC_URL_RE.search(url)
    return BULLETIN_URL_TEMPLATE.format(code=m.group(1).lower()) if m else None


def admin_url_to_id(url: str) -> str | None:
    """admin.govdelivery.com URLs carry the decimal message ID directly."""
    m = _ADMIN_URL_RE.search(url)
    if not m:
        return None
    numeric = int(m.group(1))
    return str(numeric) if numeric >= MODERN_ID_FLOOR else None


def is_lnks_url(url: str) -> bool:
    return bool(_LNKS_URL_RE.match(url))


def parse_subject_line(text: str) -> tuple[str | None, str]:
    """Split 'CSMS # 69302472 - Subject...' into (id, clean subject)."""
    m = _SUBJECT_RE.match(text or "")
    if not m:
        return None, " ".join((text or "").split())
    return m.group(1), " ".join(m.group(2).split())


def slugify(name: str, max_len: int = 80) -> str:
    """Filesystem/S3-safe lowercase slug preserving the file extension."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower() or "file"
    ext = re.sub(r"[^a-zA-Z0-9]", "", ext).lower()
    stem = stem[:max_len]
    return f"{stem}.{ext}" if ext else stem
