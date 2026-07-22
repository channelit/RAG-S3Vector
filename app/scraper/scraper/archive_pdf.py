"""Archive source: CBP's published CSMS archive PDFs.

The archive landing page https://www.cbp.gov/document/publications/csms-archive
hosts several PDFs whose internals differ by era:

  * 2011–2015  — link annotations point straight at public bulletin URLs.
  * 2016–2020  — link annotations are lnks.gd short links (resolved lazily,
                 one per message, at processing time).
  * 2021+      — the text layer is a table "CSMS # | Message Title | Sent";
                 message IDs are extracted from text and turned into bulletin
                 URLs directly (ID in hex). Row hyperlinks (lnks.gd /
                 admin.govdelivery) are redundant there and dropped.

Discovery only — all metadata comes from fetching each bulletin page.
"""

import logging
import os
import re
import tempfile

from .csms import (
    MODERN_ID_FLOOR,
    MessageRef,
    admin_url_to_id,
    bulletin_url_for_id,
    canonical_bulletin_url,
    is_lnks_url,
)
from .web import WebClient

logger = logging.getLogger(__name__)

ARCHIVE_LANDING_PAGE = "https://www.cbp.gov/document/publications/csms-archive"

# Known editions as of July 2026 — `archive --discover` scrapes the landing
# page for the current set, so new monthly PDFs don't require a code change.
KNOWN_ARCHIVES: dict[str, str] = {
    "2011-2015": "https://www.cbp.gov/sites/default/files/2024-11/CSMS%202011-2015%20508.pdf",
    "2016-2020": "https://www.cbp.gov/sites/default/files/assets/documents/2023-Oct/23_1013_csms-archive-2016-2020.pdf",
    "2021-2025": "https://www.cbp.gov/sites/default/files/2026-01/csms_archive_incl_dec2025.pdf",
    "latest-month": "https://www.cbp.gov/sites/default/files/2026-07/26_0716_ACE_csms_archive.pdf",
}

_TEXT_ID_RE = re.compile(r"\b(\d{8,9})\b")
_LEGACY_ID_RE = re.compile(r"\b\d{2}-\d{6}\b")
_PDF_HREF_RE = re.compile(r'href="([^"]*\.pdf[^"]*)"', re.IGNORECASE)

# If the text layer yields at least this many modern IDs AND no legacy IDs,
# the PDF is a pure table-format edition and its row links are duplicates —
# drop them. When legacy IDs (YY-NNNNNN) appear, the links are the only way
# to reach those messages (e.g. the 2016-2020 edition mixes both eras).
_TEXT_RICH_THRESHOLD = 10


def discover_archive_pdfs(client: WebClient) -> list[str]:
    """Scrape the archive landing page for the currently posted PDF URLs."""
    logger.info("Discovering archive PDFs from %s", ARCHIVE_LANDING_PAGE)
    resp = client.get(ARCHIVE_LANDING_PAGE)
    urls: list[str] = []
    for href in _PDF_HREF_RE.findall(resp.text):
        if "csms" not in href.lower():
            continue
        if href.startswith("/"):
            href = "https://www.cbp.gov" + href
        if href not in urls:
            urls.append(href)
    logger.info("Found %d archive PDF(s) on landing page", len(urls))
    return urls


def refs_from_archive_pdf(client: WebClient, source: str) -> list[MessageRef]:
    """Extract ordered, deduplicated message refs from one archive PDF
    (local path or URL)."""
    from pypdf import PdfReader  # local import: only archive mode needs pypdf

    local_path = source
    cleanup = False
    if re.match(r"https?://", source):
        fd, local_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        logger.info("Downloading archive PDF %s", source)
        size = client.download(source, local_path)
        logger.info("Archive PDF downloaded: %d bytes", size)
        cleanup = True

    try:
        reader = PdfReader(local_path)
        logger.info("Archive PDF %s: %d page(s)", source, len(reader.pages))

        text_ids: list[str] = []
        seen_ids: set[str] = set()
        link_refs: list[MessageRef] = []
        seen_links: set[str] = set()
        legacy_id_count = 0

        for page in reader.pages:
            page_text = page.extract_text() or ""
            legacy_id_count += len(_LEGACY_ID_RE.findall(page_text))
            for match in _TEXT_ID_RE.finditer(page_text):
                if int(match.group(1)) >= MODERN_ID_FLOOR and match.group(1) not in seen_ids:
                    seen_ids.add(match.group(1))
                    text_ids.append(match.group(1))

            if "/Annots" not in page:
                continue
            for annot in page["/Annots"]:
                try:
                    obj = annot.get_object()
                    if obj.get("/Subtype") != "/Link" or not obj.get("/A"):
                        continue
                    uri = obj["/A"].get("/URI")
                except Exception as exc:  # malformed annotation
                    logger.debug("Skipping annotation: %s", exc)
                    continue
                if not uri:
                    continue
                uri = str(uri).strip()
                if uri in seen_links:
                    continue
                seen_links.add(uri)

                admin_id = admin_url_to_id(uri)
                public_url = canonical_bulletin_url(uri)
                if admin_id:
                    link_refs.append(MessageRef(message_id=admin_id))
                elif public_url:
                    link_refs.append(MessageRef(url=public_url))
                elif is_lnks_url(uri):
                    link_refs.append(MessageRef(lnks_url=uri))
                # anything else (mailto:, cbp.gov nav links, ...) is ignored

        text_refs = [MessageRef(message_id=mid, url=bulletin_url_for_id(mid)) for mid in text_ids]

        if len(text_ids) >= _TEXT_RICH_THRESHOLD and legacy_id_count == 0:
            logger.info(
                "Table-format archive: %d IDs from text layer (dropping %d redundant row link(s))",
                len(text_ids), len(link_refs),
            )
            return text_refs

        # Mixed or link-only edition. Text refs go first (no resolution cost);
        # links follow and are the only route to legacy-ID messages. Overlap is
        # deduplicated in the pipeline, which tracks processed message IDs.
        logger.info(
            "Link-format archive: %d text ID(s), %d hyperlink ref(s), %d legacy ID mention(s)",
            len(text_ids), len(link_refs), legacy_id_count,
        )
        return text_refs + link_refs
    finally:
        if cleanup:
            os.unlink(local_path)
