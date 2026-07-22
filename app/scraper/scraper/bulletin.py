"""Fetch and parse a single GovDelivery CSMS bulletin page.

Page anatomy (identical for modern and migrated-legacy bulletins):
    <h1 class='bulletin_subject'>CSMS # 69302472 - Subject...</h1>
    <span class='dateline'>U.S. Customs and Border Protection sent this bulletin at 07/21/2026 05:26 PM EDT</span>
    <div id='bulletin_body'>...content, incl. attachment links...</div>
Attachments live under https://content.govdelivery.com/attachments/USDHSCBP/...
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from .csms import parse_subject_line
from .web import WebClient

logger = logging.getLogger(__name__)

_DATELINE_RE = re.compile(
    r"sent this bulletin at\s+(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s+[AP]M)\s+([A-Z]{2,4})"
)

_TZ_OFFSET_HOURS = {
    "EST": -5, "EDT": -4, "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6, "PST": -8, "PDT": -7, "UTC": 0, "GMT": 0,
}

_ATTACHMENT_HOST = "content.govdelivery.com"
_ATTACHMENT_PATH_PREFIX = "/attachments/"


@dataclass
class Attachment:
    url: str
    filename: str  # original filename as published (URL basename, decoded)


@dataclass
class Bulletin:
    message_id: str
    subject: str
    url: str
    sent_at: datetime | None          # timezone-aware, None if dateline unparseable
    sent_raw: str                     # dateline text as published, e.g. "07/21/2026 05:26 PM EDT"
    body_text: str
    attachments: list[Attachment] = field(default_factory=list)


def parse_sent_datetime(raw: str) -> datetime | None:
    """Parse '07/21/2026 05:26 PM EDT' into an aware datetime."""
    m = _DATELINE_RE.search(f"sent this bulletin at {raw}") if "sent this bulletin" not in raw else _DATELINE_RE.search(raw)
    if not m:
        return None
    stamp, tz_name = m.groups()
    try:
        naive = datetime.strptime(stamp, "%m/%d/%Y %I:%M %p")
    except ValueError:
        return None
    offset = _TZ_OFFSET_HOURS.get(tz_name)
    if offset is None:
        logger.warning("Unknown timezone %r in dateline — assuming Eastern (-5)", tz_name)
        offset = -5
    return naive.replace(tzinfo=timezone(timedelta(hours=offset)))


_BLOCK_TAGS = ["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol"]


def _extract_body_text(soup: BeautifulSoup) -> str:
    body = soup.select_one("#bulletin_body") or soup.select_one(".bulletin_body")
    if body is None:
        return ""
    # Break lines at block boundaries only — bulletins are dense with inline
    # spans, and a plain get_text("\n") shreds sentences into fragments.
    for br in body.find_all("br"):
        br.replace_with("\n")
    for block in body.find_all(_BLOCK_TAGS):
        block.append("\n")
    lines = [" ".join(ln.split()) for ln in body.get_text("").splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln:
            out.append(ln)
        elif out and out[-1] != "":
            out.append("")  # collapse runs of blank lines to one
    return "\n".join(out).strip()


def _extract_attachments(soup: BeautifulSoup) -> list[Attachment]:
    seen: set[str] = set()
    attachments: list[Attachment] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        parsed = urlparse(href)
        if parsed.netloc != _ATTACHMENT_HOST or not parsed.path.startswith(_ATTACHMENT_PATH_PREFIX):
            continue
        clean = parsed._replace(query="", fragment="").geturl()
        if clean in seen:
            continue
        seen.add(clean)
        filename = unquote(parsed.path.rsplit("/", 1)[-1]) or "attachment"
        attachments.append(Attachment(url=clean, filename=filename))
    return attachments


def fetch_bulletin(client: WebClient, url: str) -> Bulletin:
    logger.info("Fetching bulletin %s", url)
    resp = client.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    h1 = soup.select_one("h1.bulletin_subject") or soup.find("title")
    title_text = h1.get_text(" ", strip=True) if h1 else ""
    message_id, subject = parse_subject_line(title_text)
    if not message_id:
        raise ValueError(f"Could not parse CSMS ID from bulletin title {title_text!r} at {url}")

    dateline_el = soup.select_one("span.dateline")
    dateline = dateline_el.get_text(" ", strip=True) if dateline_el else ""
    m = _DATELINE_RE.search(dateline)
    sent_raw = f"{m.group(1)} {m.group(2)}" if m else ""
    sent_at = parse_sent_datetime(dateline) if dateline else None
    if sent_at is None:
        logger.warning("Could not parse dateline %r for message %s", dateline, message_id)

    body_text = _extract_body_text(soup)
    attachments = _extract_attachments(soup)
    logger.info(
        "Parsed CSMS %s: subject=%r sent=%s body_chars=%d attachments=%d",
        message_id, subject[:80], sent_raw or "?", len(body_text), len(attachments),
    )
    return Bulletin(
        message_id=message_id,
        subject=subject,
        url=url,
        sent_at=sent_at,
        sent_raw=sent_raw,
        body_text=body_text,
        attachments=attachments,
    )
