"""Entrata-hosted sites (e.g. renewmarinashores.com).

The configured URL is the floorplans listing page (`.fp-card` per plan). Plans with
availability link to a detail page whose `.fp-units-table` lists individual units.
These sites sit behind Cloudflare, so pages are loaded through a real browser.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from .fetch import Browser, parse_date, to_float, to_int
from .models import FloorPlan, PropertyInfo, Unit

log = logging.getLogger(__name__)


def _text(el: Optional[Tag]) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _cell_text(cell: Tag) -> str:
    """Cell text minus the labels Entrata injects for mobile layouts."""
    for label in cell.select(".mobile-text, .small-text"):
        label.decompose()
    return _text(cell)


def parse_property(page: str) -> PropertyInfo:
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        if data.get("@type") != "ApartmentComplex":
            continue
        addr = data.get("address") or {}
        parts = [addr.get("streetAddress"), addr.get("addressLocality"), addr.get("addressRegion"), addr.get("postalCode")]
        phone = re.sub(r"\D", "", data.get("telephone") or "")
        if len(phone) == 10:
            phone = f"{phone[:3]}-{phone[3:6]}-{phone[6:]}"
        return PropertyInfo(address=", ".join(p.strip() for p in parts if p) or None, phone=phone or None)
    return PropertyInfo()


def parse_floorplans(page: str, today: Optional[date] = None) -> List[FloorPlan]:
    soup = BeautifulSoup(page, "html.parser")
    cards = soup.select(".fp-card")
    if not cards:
        raise ValueError("No .fp-card elements found; site template may have changed")
    plans = []
    for card in cards:
        name = _text(card.select_one(".fp-title"))
        link = card.select_one("a.fp-view-details-btn")
        details_url = link["href"] if link else None
        m = re.search(r"-(\d+)/fp_name", details_url or "")
        code = m.group(1) if m else name

        size = _text(card.select_one(".dynamic-text-before"))  # "1 Bed / 1 Bath" or "Studio / 1 Bath"
        beds_m = re.search(r"([\d.]+)\s*Bed", size)
        baths_m = re.search(r"([\d.]+)\s*Bath", size)
        beds = 0.0 if "studio" in size.lower() else (to_float(beds_m.group(1)) if beds_m else None)

        rent_min = rent_max = None
        calc = card.select_one(".calculate-btn[data-url]")
        if calc:
            qs = parse_qs(urlparse(calc["data-url"]).query)
            rent_min = to_int(qs.get("min_rent", [None])[0])
            rent_max = to_int(qs.get("max_rent", [None])[0])
        if rent_min is None:
            price = re.search(r"\$[\d,]+", _text(card.select_one(".fee-transparency-text")))
            rent_min = to_int(price.group()) if price else None

        avail = _text(card.select_one(".availability"))
        count_m = re.search(r"(\d+)\s+Units?\s+Available", avail, re.I)
        date_m = re.search(r"Available\s+(\w{3,9} \d{1,2}, \d{4})", avail)
        if count_m:
            units_available = int(count_m.group(1))
        elif rent_min is not None and "waitlist" not in avail.lower():
            units_available = 1  # e.g. "Available Nov 17, 2026"; refined from the detail page
        else:
            units_available = 0

        img = card.select_one(".fp-img a[data-url]") or card.select_one(".fp-img img")
        plans.append(
            FloorPlan(
                code=code,
                name=name,
                beds=beds,
                baths=to_float(baths_m.group(1)) if baths_m else None,
                sqft=to_int(_text(card.select_one(".dynamic-text-after"))),
                rent_min=rent_min if units_available else None,
                rent_max=rent_max if units_available else None,
                units_available=units_available,
                earliest_available=parse_date(date_m.group(1)) if date_m else None,
                image_url=(img.get("data-url") or img.get("src")) if img else None,
                details_url=details_url,
                specials=[_text(s) for s in card.select(".fp-special-name")],
            )
        )
    return plans


def parse_units(page: str, floorplan_code: str, today: Optional[date] = None) -> List[Unit]:
    soup = BeautifulSoup(page, "html.parser")
    units = []
    for table in soup.select(".fp-units-table"):
        header = table.select_one(".option-row.title")
        if not header:
            continue
        columns = [_text(c).lower() for c in header.find_all("div", class_="detail", recursive=False)]
        for row in table.select(".option-row"):
            if "title" in row.get("class", []):
                continue
            cells = row.find_all("div", class_="detail", recursive=False)
            values = {col: _cell_text(cell) for col, cell in zip(columns, cells)}
            number = values.get("unit")
            if not number:
                continue
            price = re.search(r"\$[\d,]+", values.get("rent", ""))
            units.append(
                Unit(
                    unit_number=number,
                    floorplan_code=floorplan_code,
                    price=to_int(price.group()) if price else None,
                    sqft=to_int(values.get("sq.ft.")),
                    building=values.get("building") or None,
                    available_date=parse_date(values.get("available"), today),
                )
            )
    return units


def scrape(cfg: dict, today: Optional[date] = None) -> Tuple[PropertyInfo, List[FloorPlan], List[Unit]]:
    units: List[Unit] = []
    with Browser() as browser:
        listing = browser.get(cfg["url"])
        info = parse_property(listing)
        floorplans = parse_floorplans(listing, today)
        for fp in floorplans:
            if not fp.units_available or not fp.details_url:
                continue
            fp_units = parse_units(browser.get(fp.details_url), fp.code, today)
            if not fp_units:
                log.warning("%s: no unit rows on %s", cfg["slug"], fp.details_url)
                continue
            fp.units_available = len(fp_units)
            prices = [u.price for u in fp_units if u.price]
            if prices:
                fp.rent_min = min(prices)
            dates = sorted(u.available_date for u in fp_units if u.available_date)
            if dates:
                fp.earliest_available = dates[0]
            units.extend(fp_units)
    return info, floorplans, units
