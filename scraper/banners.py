"""Site-wide promo banners ("Move in by Oct 31 and enjoy $500 off 2-bedroom homes!").

Some specials appear only in a homepage banner, not in floorplan/unit data. Complexes opt in
with a `banner:` entry in complexes.yaml ({url, selector}); the page is fetched over plain HTTP
and promo-looking text is kept only if `parse_special` understands a discount in it, so
"Deposit Free Community" or "Free bicycle rentals" are ignored. Banners rendered by JavaScript
(popups) aren't visible this way.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Dict, List, Optional

from bs4 import BeautifulSoup, Tag

from .fetch import http_get
from .specials import parse_special

log = logging.getLogger(__name__)

PROMO_RE = re.compile(r"\bfree\b|\$\s?\d[\d,]*\s*off\b|\bmove[\s-]*in\b", re.I)
MAX_BANNERS = 5


def _text(el: Tag) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


def _heading_before(el: Tag) -> str:
    """Short heading just above the banner text (e.g. "FALL INTO SAVINGS TODAY!"), if any."""
    prev = el.find_previous(re.compile(r"^h[1-6]$"))
    text = _text(prev) if prev else ""
    return text if text and len(text) <= 80 and not PROMO_RE.search(text) else ""


def _fine_print_after(el: Tag) -> str:
    """A "*All offers... 12+ month leases" note right after the banner, which carries its conditions."""
    nxt = el.find_next_sibling()
    text = _text(nxt) if nxt else ""
    return text if text.startswith("*") and len(text) <= 300 else ""


def parse_banners(html: str, selector: Optional[str] = None, ref: Optional[date] = None) -> List[Dict[str, str]]:
    """[{title, description}] for each promo with an understood discount, innermost elements only."""
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup(["script", "style", "noscript", "template"]):
        junk.decompose()
    roots = soup.select(selector) if selector else [soup]
    out, seen = [], set()
    for root in roots:
        for el in root.find_all(True):
            text = _text(el)
            if not (8 <= len(text) <= 250 and PROMO_RE.search(text)):
                continue
            # Innermost match only: skip containers whose child already holds the promo text.
            if any(PROMO_RE.search(_text(c)) and len(_text(c)) >= 8 for c in el.find_all(True, recursive=False)):
                continue
            if text.lower() in seen or not parse_special(text, "", ref).parsed:
                continue
            seen.add(text.lower())
            desc = " — ".join(x for x in (_heading_before(el), _fine_print_after(el)) if x)
            out.append({"title": text, "description": desc})
            if len(out) >= MAX_BANNERS:
                return out
    return out


def scrape_banners(cfg: dict, today: Optional[date] = None) -> List[Dict[str, str]]:
    banner = cfg.get("banner") or {}
    url = banner.get("url") or cfg.get("website") or cfg["url"]
    found = parse_banners(http_get(url), banner.get("selector"), today)
    log.info("%s: %d site-wide banner special(s)", cfg["slug"], len(found))
    return found
