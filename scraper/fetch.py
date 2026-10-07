"""HTTP and headless-browser fetching."""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from typing import Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


def http_get(url: str) -> str:
    resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    return resp.text


class Browser:
    """Playwright session for sites behind a Cloudflare check.

    Prefers the installed Google Chrome (passes the check headless); falls back to
    Playwright's bundled Chromium.
    """

    def __enter__(self) -> "Browser":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        args = ["--disable-blink-features=AutomationControlled"]
        try:
            self._browser = self._pw.chromium.launch(headless=True, channel="chrome", args=args)
        except Exception as e:  # Chrome not installed
            log.warning("Google Chrome unavailable (%s); using bundled Chromium", e)
            self._browser = self._pw.chromium.launch(headless=True, args=args)
        self._ctx = self._browser.new_context(user_agent=USER_AGENT, viewport={"width": 1366, "height": 900})
        self._page = self._ctx.new_page()
        return self

    def __exit__(self, *exc) -> None:
        self._browser.close()
        self._pw.stop()

    def get(self, url: str, settle_ms: int = 3000) -> str:
        self._open(url, settle_ms)
        return self._page.content()

    def get_json_responses(self, url: str, match: List[str], settle_ms: int = 8000) -> Dict[str, object]:
        """Load `url` and return the JSON body of the first response whose URL contains each
        `match` substring (for sites whose data API needs a token only the page can obtain)."""
        found: Dict[str, object] = {}

        def on_response(resp):
            for m in match:
                if m not in found and m in resp.url:
                    try:
                        found[m] = resp.json()
                    except Exception:  # non-JSON (e.g. preflight); keep waiting
                        pass

        self._page.on("response", on_response)
        try:
            self._open(url, settle_ms)
        finally:
            self._page.remove_listener("response", on_response)
        missing = [m for m in match if m not in found]
        if missing:
            raise RuntimeError(f"Page never requested {missing}: {url}")
        return found

    def _open(self, url: str, settle_ms: int) -> None:
        page = self._page
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        for _ in range(30):
            if "just a moment" not in page.title().lower():
                break
            time.sleep(1.5)
        else:
            raise RuntimeError(f"Stuck on Cloudflare challenge: {url}")
        page.wait_for_timeout(settle_ms)


# --- parsing helpers -------------------------------------------------------

def to_int(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d.]", "", str(value))
    if not digits:
        return None
    return int(float(digits))


def to_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        m = re.search(r"\d+(\.\d+)?", str(value))
        return float(m.group()) if m else None


def parse_date(text: Optional[str], today: Optional[date] = None) -> Optional[str]:
    """Parse '09/25/2026', 'Nov 17, 2026', 'Now' etc. into an ISO date string."""
    if not text:
        return None
    text = text.strip()
    if text.lower() in ("now", "available now", "today"):
        return (today or date.today()).isoformat()
    for fmt in ("%m/%d/%Y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return None if d.year < 1900 else d.isoformat()
    return None
