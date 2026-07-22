"""Current-messages source: the GovDelivery widget feed embedded on
https://www.cbp.gov/trade/automated/cargo-systems-messaging-service.

The widget JSONP endpoint returns the last ~100 bulletins as
    GDWidgets[0].update([{"subject": "CSMS # NNN - ...",
                          "pub_date": "07/21/2026 05:26 PM EDT",
                          "href": "https://content.govdelivery.com/bulletins/gd/USDHSCBP-<hex>?wgt_ref=..."}, ...])
"""

import json
import logging
import re

from .csms import MessageRef, canonical_bulletin_url, parse_subject_line
from .web import WebClient

logger = logging.getLogger(__name__)

FEED_URL = "https://content.govdelivery.com/accounts/USDHSCBP/widgets/USDHSCBP_WIDGET_2/0.json"

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
