"""Polite HTTP client: shared session, per-request delay, retries with backoff,
and lnks.gd (GovDelivery link-shortener) resolution via its meta-refresh page."""

import logging
import re
import time

import requests

from .config import Settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_LNKS_META_RE = re.compile(
    r'http-equiv="refresh"\s+content="\d+;\s*url=([^"]+)"', re.IGNORECASE
)
_LNKS_DEST_RE = re.compile(r'id="destination"[^>]*\bhref="([^"]+)"|\bhref="([^"]+)"[^>]*id="destination"')


class WebClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._session = requests.Session()
        self._session.headers["User-Agent"] = settings.user_agent
        self._last_request_at = 0.0

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_at
        wait = self._settings.request_delay - elapsed
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str, stream: bool = False) -> requests.Response:
        """GET with throttle + retry. Raises for non-2xx after retries."""
        last_exc: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 1):
            self._throttle()
            try:
                self._last_request_at = time.monotonic()
                resp = self._session.get(
                    url, timeout=self._settings.request_timeout, stream=stream
                )
                if resp.status_code in _RETRYABLE_STATUS:
                    raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                resp.raise_for_status()
                return resp
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status is not None and status not in _RETRYABLE_STATUS:
                    raise  # 403/404 etc — retrying will not help
                last_exc = exc
            except requests.RequestException as exc:
                last_exc = exc
            backoff = 2 ** attempt
            logger.warning(
                "GET %s failed (attempt %d/%d): %s — retrying in %ds",
                url, attempt, self._settings.max_retries, last_exc, backoff,
            )
            time.sleep(backoff)
        raise RuntimeError(f"GET {url} failed after {self._settings.max_retries} attempts: {last_exc}")

    def download(self, url: str, dest_path: str) -> int:
        """Stream a file to disk, return bytes written."""
        resp = self.get(url, stream=True)
        written = 0
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
                written += len(chunk)
        return written

    def resolve_lnks(self, url: str) -> str | None:
        """Resolve a lnks.gd short link to its destination URL.

        lnks.gd returns HTTP 200 with a meta-refresh page rather than a 3xx,
        so the destination has to be scraped out of the HTML.
        """
        try:
            resp = self.get(url)
        except Exception as exc:
            logger.warning("lnks.gd resolution failed for %s: %s", url, exc)
            return None
        m = _LNKS_META_RE.search(resp.text)
        if not m:
            m = _LNKS_DEST_RE.search(resp.text)
            if m:
                return (m.group(1) or m.group(2)).strip()
            logger.warning("No redirect target found in lnks.gd page %s", url)
            return None
        return m.group(1).strip()
