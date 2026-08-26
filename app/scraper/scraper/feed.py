"""Current-messages sources.

Two independent live feeds, unioned by list_current_messages():

  * The GovDelivery widget feed embedded on
    https://www.cbp.gov/trade/automated/cargo-systems-messaging-service.
    Its JSONP endpoint returns the last ~100 CSMS bulletins as
        GDWidgets[0].update([{"subject": "CSMS # NNN - ...",
                              "pub_date": "07/21/2026 05:26 PM EDT",
                              "href": "https://content.govdelivery.com/bulletins/gd/USDHSCBP-<hex>?wgt_ref=..."}, ...])

  * The account-wide RSS feed
    https://public.govdelivery.com/accounts/USDHSCBP/feed.rss — the last ~25
    USDHSCBP bulletins of EVERY topic (Newsroom, media releases, TIN/CAMS/PGA,
    ...), so items are kept only when the <title> parses as a CSMS subject.
    Shallower than the widget feed but a standard format, so it doubles as a
    fallback when the widget JSONP shape changes.
"""

import json
import logging
import re
import xml.etree.ElementTree as ET

from .csms import MessageRef, canonical_bulletin_url, parse_subject_line
from .web import WebClient

logger = logging.getLogger(__name__)

FEED_URL = "https://content.govdelivery.com/accounts/USDHSCBP/widgets/USDHSCBP_WIDGET_2/0.json"
RSS_FEED_URL = "https://public.govdelivery.com/accounts/USDHSCBP/feed.rss"

# The payload is JSONP — GDWidgets[0].update([...]) — so the array must be
# pulled out of the update(...) call, not just the first [...] in the text
# (which would match the [0] subscript).
_JSON_ARRAY_RE = re.compile(r"\.update\(\s*(\[.*\])\s*\)", re.DOTALL)


def list_feed_messages(client: WebClient) -> list[MessageRef]:
    """Return refs for the most recent messages, newest first."""
    logger.info("Fetching live feed: %s", FEED_URL)
    resp = client.get(FEED_URL)
    m = _JSON_ARRAY_RE.search(resp.text)
    if not m:
        raise RuntimeError("Widget feed did not contain a JSON array — format changed?")
    items = json.loads(m.group(1))
    logger.info("Feed contains %d item(s)", len(items))

    refs: list[MessageRef] = []
    for item in items:
        subject_raw = item.get("subject", "")
        message_id, subject = parse_subject_line(subject_raw)
        url = canonical_bulletin_url(item.get("href", ""))
        if not message_id and not url:
            logger.warning("Skipping unparseable feed item: %r", subject_raw)
            continue
        refs.append(
            MessageRef(
                message_id=message_id,
                url=url,
                subject_hint=subject,
                pub_date_hint=item.get("pub_date"),
            )
        )
    return refs


def list_rss_messages(client: WebClient) -> list[MessageRef]:
    """Return refs for the CSMS items in the account-wide RSS feed, newest first."""
    logger.info("Fetching RSS feed: %s", RSS_FEED_URL)
    resp = client.get(RSS_FEED_URL)
    root = ET.fromstring(resp.text)
    items = root.findall(".//item")

    refs: list[MessageRef] = []
    for item in items:
        title = " ".join((item.findtext("title") or "").split())
        message_id, subject = parse_subject_line(title)
        if not message_id:
            continue  # Newsroom / media-release / TIN / CAMS / PGA bulletin
        url = canonical_bulletin_url(item.findtext("link") or "")
        refs.append(
            MessageRef(
                message_id=message_id,
                url=url,
                subject_hint=subject,
                pub_date_hint=(item.findtext("pubDate") or "").strip() or None,
            )
        )
    logger.info("RSS feed contains %d item(s), %d CSMS", len(items), len(refs))
    return refs


def list_current_messages(client: WebClient) -> list[MessageRef]:
    """Union of the widget and RSS feeds, deduped, newest first per source.

    Either source failing alone is survivable (they overlap almost entirely);
    the run only fails if both are unreadable.
    """
    refs: list[MessageRef] = []
    failures = 0
    for source in (list_feed_messages, list_rss_messages):
        try:
            refs.extend(source(client))
        except Exception as exc:
            failures += 1
            logger.warning("%s failed: %s", source.__name__, exc)
    if failures == 2:
        raise RuntimeError("Both live feeds (widget JSON and RSS) failed")

    seen: set[str] = set()
    unique: list[MessageRef] = []
    for ref in refs:
        key = ref.message_id or ref.url
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique
