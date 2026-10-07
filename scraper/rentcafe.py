"""Yardi RentCafe property sites (e.g. linkhornbayapartments-prg.com).

The configured URL is the /floorplans page: one `.fp-container` card per plan with
beds/baths/sqft, "Starting at" price and an "N Available" count (the count can be capped,
see `data-max`). Each plan's detail page (/floorplans/<slug>) lists its units as
`tr.unit-container` rows: apartment #, sq ft, rent range, amenities, available date and
an apply link. Plain HTTP works.

Some RentCafe sites don't publish prices ("Rent: Call"); units are still tracked, with
price None.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .entrata import parse_property  # same schema.org ApartmentComplex JSON-LD
from .fetch import http_get, parse_date, to_float, to_int
from .models import FloorPlan, PropertyInfo, Unit

log = logging.getLogger(__name__)
FLOOR_WORDS = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "ground": "1", "top": None}


def _text(el: Optional[Tag]) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _cell(row: Tag, cls: str) -> str:
    cell = row.select_one(f"td.{cls}")
    if not cell:
        return ""
    for label in cell.select(".td-label, .sr-only"):
        label.decompose()
    return _text(cell)


def parse_floorplans(page: str, base_url: str, today: Optional[date] = None) -> List[FloorPlan]:
    soup = BeautifulSoup(page, "html.parser")
    cards = soup.select(".fp-container")
    if not cards:
        raise ValueError("No .fp-container cards found; site template may have changed")
    plans = []
    for card in cards:
        code = (card.get("id") or "").replace("fp-container-", "") or _text(card.select_one(".card-title"))
        name = _text(card.select_one(".card-title"))
        header = _text(card.select_one(".card-header"))
        beds = re.search(r"([\d.]+)\s*Bed", header)
        baths = re.search(r"([\d.]+)\s*Bath", header)
        sqft = re.search(r"([\d,]+)\s*Sq\.?\s*Ft", header)
        avail = card.select_one(".fp-availability")
        count = re.search(r"(\d+)", _text(avail)) if avail else None
        price = re.search(r"Starting at\s*\$([\d,]+(?:\.\d+)?)", _text(card))
        link = next((a for a in card.select("a[href]") if "/floorplans/" in a["href"]), None)
        # Some sites (Indigo 19) show "Call for Details" with no plan link, but the plan page
        # still exists at /floorplans/<name-slug> and lists units (without prices).
        href = link["href"] if link else "/floorplans/" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        img = card.select_one("img")
        units_available = int(count.group(1)) if count else 0
        plans.append(FloorPlan(
            code=code,
            name=name,
            beds=0.0 if "studio" in header.lower() else (to_float(beds.group(1)) if beds else None),
            baths=to_float(baths.group(1)) if baths else None,
            sqft=to_int(sqft.group(1)) if sqft else None,
            rent_min=to_int(price.group(1)) if price and units_available else None,
            units_available=units_available,
            image_url=img.get("src") if img else None,
            details_url=urljoin(base_url, href) if name else None,
        ))
    return plans


def parse_units(page: str, floorplan_code: str, today: Optional[date] = None) -> List[Unit]:
    soup = BeautifulSoup(page, "html.parser")
    units = []
    for row in soup.select("tr.unit-container"):
        number = _cell(row, "td-card-name").lstrip("#").strip()
        if not number:
            continue
        rents = [to_int(p) for p in re.findall(r"\$([\d,]+(?:\.\d+)?)", _cell(row, "td-card-rent"))]
        amenities = [_text(li) for li in row.select("td.td-card-details li")]
        floor = None
        for a in amenities:
            m = re.match(r"(\w+)\s+Floor", a, re.I)
            if m:
                floor = FLOOR_WORDS.get(m.group(1).lower(), m.group(1) if m.group(1).isdigit() else None)
        apply = row.select_one("td.td-card-footer a[href]")
        units.append(Unit(
            unit_number=number,
            floorplan_code=floorplan_code,
            price=min(rents) if rents else None,  # range spans lease terms/move-in dates; lowest is the headline
            sqft=to_int(_cell(row, "td-card-sqft")),
            floor=floor,
            available_date=parse_date(_cell(row, "td-card-available"), today),
            apply_url=apply["href"].strip() if apply else None,
        ))
    return units or _parse_unit_cards(soup, floorplan_code, today)


def _parse_unit_cards(soup: BeautifulSoup, floorplan_code: str, today: Optional[date]) -> List[Unit]:
    """Card layout used by some RentCafe sites (Salt Meadow Bay): `#availApts .card`, each with
    "Apartment: # 0837-210", "Available Now" or a date, "Starting at: $X" (the total when
    labeled "Total Monthly Leasing Price") and "Base rent $Y · 9-month term"."""
    units = []
    for card in soup.select("#availApts .card"):
        title = _text(card.select_one(".card-title"))
        number = re.sub(r"^.*?#\s*", "", title).strip()
        if not number:
            continue
        text = _text(card)
        start = re.search(r"Starting at:\s*\$([\d,]+(?:\.\d+)?)", text)
        base = re.search(r"Base rent\s*\$([\d,]+(?:\.\d+)?)", text)
        term = re.search(r"(\d{1,2})-month term", text)
        is_total = "Total Monthly Leasing Price" in text
        avail = next((_text(p) for p in card.select(".card-subtitle") if "Available" in _text(p)), "")
        apply = card.select_one("a.btn-primary[href]")
        sqft = card.select_one("[data-floorplan-sqft]")
        units.append(Unit(
            unit_number=number,
            floorplan_code=floorplan_code,
            price=to_int(base.group(1)) if base else (to_int(start.group(1)) if start and not is_total else None),
            total_price=to_int(start.group(1)) if start and is_total else None,
            sqft=to_int(sqft["data-floorplan-sqft"]) if sqft else None,
            available_date=parse_date(re.sub(r"^(Date\s+)?Available:?\s*(on\s*)?", "", avail, flags=re.I) or None, today),
            apply_url=apply["href"].strip() if apply else None,
            lease_months=int(term.group(1)) if term else None,
        ))
    return units


def scrape(cfg: dict, today: Optional[date] = None) -> Tuple[PropertyInfo, List[FloorPlan], List[Unit]]:
    listing = http_get(cfg["url"])
    info = parse_property(listing)
    floorplans = parse_floorplans(listing, cfg["url"], today)
    units: List[Unit] = []
    for fp in floorplans:
        if not fp.units_available or not fp.details_url:
            continue
        fp_units = parse_units(http_get(fp.details_url), fp.code, today)
        if not fp_units:
            log.warning("%s: no unit rows on %s", cfg["slug"], fp.details_url)
            continue
        for u in fp_units:
            u.sqft = u.sqft or fp.sqft
        fp.units_available = len(fp_units)
        prices = [u.price for u in fp_units if u.price]
        if prices:
            fp.rent_min, fp.rent_max = min(prices), max(prices)
        dates = sorted(u.available_date for u in fp_units if u.available_date)
        fp.earliest_available = dates[0] if dates else None
        units.extend(fp_units)
    return info, floorplans, units
