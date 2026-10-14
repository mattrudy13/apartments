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
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import yaml
from bs4 import BeautifulSoup, Tag

from .fetch import Browser, parse_date, to_float, to_int
from .models import FloorPlan, PropertyInfo, Unit

log = logging.getLogger(__name__)
PRICE_BASIS = "total"  # prices are "Total Monthly Leasing Price" (rent + required fees)
TERMS_PAUSE = (5.0, 10.0)  # seconds between per-unit lease-term requests (same as page loads)
# Lease terms are fetched only for units that could be viable: a viable bed count, quoted under
# max_monthly plus this share. ReNew rate-limits (~28 term requests got a 429 on 2026-10-10 and
# 10-13); this cut it to ~10 on 10-05's units. Specials are applied later from the quote either way.
TERMS_MARGIN = 0.15
VIABLE_CONFIG = Path(__file__).resolve().parent.parent / "viable.yaml"


def _text(el: Optional[Tag]) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _cell_text(cell: Tag) -> str:
    """Cell text minus the labels Entrata injects for mobile layouts."""
    for label in cell.select(".mobile-text, .small-text"):
        label.decompose()
    return _text(cell)


def _lease_months(el: Optional[Tag]) -> Optional[int]:
    """'15mo lease' / '12 month lease' -> 15 / 12."""
    m = re.search(r"(\d{1,2})\s*(?:mo|month)", _text(el), re.I)
    return int(m.group(1)) if m else None


def _specials(card: Tag) -> list:
    out = []
    for block in card.select(".fp-special-main-content"):
        title = _text(block.select_one(".fp-special-name"))
        if title:
            out.append({"title": title, "description": _text(block.select_one(".lease-desc"))})
    return out


def _ld_items(page: str):
    """Every JSON-LD object on the page, including those inside @graph lists."""
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict):
                yield from (x for x in item.get("@graph", [item]) if isinstance(x, dict))


def parse_property(page: str) -> PropertyInfo:
    """Address/phone from the schema.org ApartmentComplex JSON-LD (shared by most scrapers)."""
    for data in _ld_items(page):
        types = data.get("@type")
        if "ApartmentComplex" not in (types if isinstance(types, list) else [types]):
            continue
        addr = data.get("address") or {}
        if isinstance(addr, list):
            addr = addr[0] if addr else {}
        if isinstance(addr, str):
            addr = {"streetAddress": addr}
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
                lease_months=_lease_months(card.select_one(".lease-term-name")),
                specials=_specials(card),
            )
        )
    return plans


def _unit_rows(page: str, floorplan_code: str, today: Optional[date] = None):
    """(row element, Unit) for each unit row in the detail page's `.fp-units-table`."""
    soup = BeautifulSoup(page, "html.parser")
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
            lease_months = _lease_months(row.select_one(".lease-term-name"))
            price = re.search(r"\$[\d,]+", values.get("rent", ""))
            yield row, Unit(
                unit_number=number,
                floorplan_code=floorplan_code,
                price=to_int(price.group()) if price else None,
                sqft=to_int(values.get("sq.ft.")),
                building=values.get("building") or None,
                available_date=parse_date(values.get("available"), today),
                lease_months=lease_months,
            )


def parse_units(page: str, floorplan_code: str, today: Optional[date] = None) -> List[Unit]:
    return [u for _, u in _unit_rows(page, floorplan_code, today)]


def unit_space_ids(page: str) -> dict:
    """{(building, unit number): Entrata unit-space id} from each unit row's "See Details" button,
    which the lease-terms request needs."""
    out = {}
    for row, u in _unit_rows(page, ""):
        btn = row.select_one(".js-show-details[data-unit]")
        if btn:
            out[(u.building, u.unit_number)] = btn["data-unit"]
    return out


def parse_lease_terms(page: str) -> List[dict]:
    """The "See Details" lease-term boxes -> [{months, price}]. Prices are Entrata's total monthly
    price (PRICE_BASIS "total"), so there's no separate total."""
    soup = BeautifulSoup(page, "html.parser")
    out = {}
    for box in soup.select(".js-select-term[data-term][data-rent]"):
        months, price = to_int(box["data-term"]), to_int(round(float(box["data-rent"] or 0)))
        if months and price:
            out[months] = {"months": months, "price": price, "total_price": None}
    return [out[m] for m in sorted(out)]


def lease_terms_path(listing_url: str, floorplan_id: str, unit_space_id: str) -> str:
    """The request the "See Details" button makes (relative to the site, under /<city>/<property>/)."""
    base = re.sub(r"/conventional/?$", "/floorplans/", urlparse(listing_url).path)
    return (f"{base}?module=property_floorplans&action=view_lease_term"
            f"&property_floorplan[id]={floorplan_id}&unit_space[id]={unit_space_id}&occupancy_type=c")


def load_viable(path: Path = VIABLE_CONFIG) -> dict:
    """beds / max_monthly from viable.yaml (read here because build.py imports the scrapers)."""
    cfg = (yaml.safe_load(path.read_text()) if path.exists() else None) or {}
    return {"beds": [float(b) for b in cfg.get("beds") or []], "max_monthly": cfg.get("max_monthly")}


def wants_terms(beds: Optional[float], price: Optional[int], viable: dict) -> bool:
    """Whether a unit is worth a lease-term request. Without a viable.yaml, every unit is."""
    if viable.get("beds") and beds not in viable["beds"]:
        return False
    limit = viable.get("max_monthly")
    return not limit or price is None or price < limit * (1 + TERMS_MARGIN)


def scrape(cfg: dict, today: Optional[date] = None) -> Tuple[PropertyInfo, List[FloorPlan], List[Unit]]:
    units: List[Unit] = []
    pending = []  # (floorplan, unit, unit-space id) still needing lease terms
    viable = load_viable()
    with Browser() as browser:
        listing = browser.get(cfg["url"])
        info = parse_property(listing)
        floorplans = parse_floorplans(listing, today)
        for fp in floorplans:
            if not fp.units_available or not fp.details_url:
                continue
            detail = browser.get(fp.details_url)
            fp_units = parse_units(detail, fp.code, today)
            if not fp_units:
                log.warning("%s: no unit rows on %s", cfg["slug"], fp.details_url)
                continue
            space_ids = unit_space_ids(detail)
            for u in fp_units:
                space = space_ids.get((u.building, u.unit_number))
                if space and wants_terms(fp.beds, u.price, viable):
                    pending.append((fp, u, space))
            fp.units_available = len(fp_units)
            prices = [u.price for u in fp_units if u.price]
            if prices:
                fp.rent_min = min(prices)
            dates = sorted(u.available_date for u in fp_units if u.available_date)
            if dates:
                fp.earliest_available = dates[0]
            units.extend(fp_units)

        # Prices for every lease term: one in-page request per unit, after every page has loaded,
        # so a rate limit (429 on 2026-10-10 and 10-13, then a Cloudflare challenge on the next
        # page load) costs only terms, never the snapshot. The first failure stops term requests;
        # units keep their quote.
        log.info("%s: fetching lease terms for %d of %d units", cfg["slug"], len(pending), len(units))
        for fp, u, space in pending:
            try:
                u.lease_options = parse_lease_terms(
                    browser.fetch(lease_terms_path(cfg["url"], fp.code, space), pause=TERMS_PAUSE))
            except Exception as e:
                log.warning("%s: lease terms failed for %s #%s, skipping the rest: %s",
                            cfg["slug"], u.building, u.unit_number, e)
                break
    return info, floorplans, units
