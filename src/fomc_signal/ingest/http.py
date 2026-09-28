"""Polite, disk-cached HTTP access to federalreserve.gov.

Every response body is written to ``data/cache/html`` keyed by URL path, and a
cached file is never downloaded again. Network requests are rate limited.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

BASE_URL = "https://www.federalreserve.gov"
USER_AGENT = "fomc-text-signal research scraper (python-requests; low volume, cached)"
MIN_INTERVAL_S = 1.5


def decode_body(raw: bytes) -> str:
    """Decode a page body: UTF-8 if valid, else Windows-1252 (used by old archive pages)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def cache_path(url: str, cache_dir: Path) -> Path:
    """Map a URL to its cache file (path with separators flattened to ``_``)."""
    parsed = urlparse(urljoin(BASE_URL, url))
    key = parsed.path.strip("/").replace("/", "_") or "index"
    key = re.sub(r"[^A-Za-z0-9._-]", "_", key)
    return cache_dir / key


class CachedFetcher:
    """Fetch pages with an on-disk cache and a minimum interval between requests."""

    def __init__(self, cache_dir: Path, min_interval_s: float = MIN_INTERVAL_S) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self._last_request = 0.0
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self.n_network = 0
        self.n_cached = 0

    @staticmethod
    def absolute(url: str) -> str:
        """Absolute URL for a site-relative path."""
        return urljoin(BASE_URL, url)

    def get(self, url: str) -> str | None:
        """Return the page body for ``url`` (absolute or site-relative), or None on 404.

        Cached bodies are returned without touching the network. A 404 is cached as
        an empty marker file so it is not retried either.
        """
        path = cache_path(url, self.cache_dir)
        missing = path.with_suffix(path.suffix + ".404")
        if path.exists():
            self.n_cached += 1
            return decode_body(path.read_bytes())
        if missing.exists():
            return None

        wait = self.min_interval_s - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        resp = self._session.get(urljoin(BASE_URL, url), timeout=30)
        self._last_request = time.monotonic()
        self.n_network += 1
        if resp.status_code == 404:
            missing.touch()
            return None
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return decode_body(resp.content)
