"""Sites that embed an Engrain SightMap (e.g. liveatnexus.com, a Greystar site).

The floorplans page embeds `https://sightmap.com/embed/<id>`; the embed page names its
data URL `https://sightmap.com/app/api/v1/<asset>/sightmaps/<n>`, a public JSON document
with every available unit (base rent, total monthly price incl. required fees, lease
term, available date) and the floor plans. Plain HTTP works.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

from .entrata import parse_property  # schema.org ApartmentComplex JSON-LD, if present
from .fetch import http_get, parse_date, to_float, to_int
from .models import FloorPlan, PropertyInfo, Unit


def _plan_name(raw: str) -> str:
    """SightMap names can be a JSON string like '{"name":"A1","provider_id":"6293270"}'."""
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("name"):
            return str(data["name"])
    except (TypeError, ValueError):
        pass
    return raw


def page_text(page: str) -> str:
    return "\n".join(line.strip() for line in BeautifulSoup(page, "html.parser").get_text("\n").splitlines() if line.strip())


def sqft_on_page(text: str, plan_name: str) -> Optional[int]:
    """Plan sqft from the floorplans page cards ("A0 / 1 bed / 1 bath / 563 sq. ft.").
    SightMap's floor plan list has no square footage, so plans without units need this."""
    m = re.search(r"(?:^|\n)%s\n(?:[^\n]*\n){1,3}?([\d,]+) sq\. ?ft" % re.escape(plan_name), text)
    return to_int(m.group(1)) if m else None


def _norm(name: str) -> str:
    """'A4.1-V' / 'A4.1V' / 'A4.1' -> 'a4.1' for matching plan names across sources."""
    return re.sub(r"[-\s]?[vh]$", "", (name or "").strip().lower())


def page_plan_details(page: str) -> dict:
    """{normalized plan name: (sqft, image)} from RealPage/Vest embedded `:floorplans` data, if the
    page has it (Attain). Fills sqft/images for plans SightMap lists without units."""
    try:
        from .realpage_craft import _prop
        plans = _prop(page, "floorplans")
    except Exception:
        return {}
    out = {}
    for f in plans:
        detail = (to_int(f.get("floorPlanInteriorSquareFeet")), f.get("floorPlanImageFull") or f.get("floorPlanImage"))
        for key in (f.get("floorPlanCode"), f.get("floorPlanName")):
            if key:
                out.setdefault(_norm(key), detail)
    return out


def parse(data: dict, today: Optional[date] = None, page: str = "") -> Tuple[List[FloorPlan], List[Unit]]:
    sm = data.get("data", data)
    # "Flat pricing" sites quote every price for one lease term (Attain: 12 months).
    flat_lease = to_int(sm.get("flat_pricing_lease_term_months")) if sm.get("pricing_strategy") == "flat_pricing" else None
    plans_by_id = {str(fp["id"]): fp for fp in sm.get("floor_plans", [])}

    units = []
    for u in sm.get("units", []):
        totals = u.get("total_price") or []
        lease = re.search(r"(\d{1,2})\s*Month", u.get("display_lease_term") or "", re.I)
        special = (u.get("specials_description") or "").strip()
        units.append(Unit(
            unit_number=str(u.get("unit_number") or u.get("label")),
            floorplan_code=str(u.get("floor_plan_id")),
            price=to_int(u.get("price")),
            total_price=round(min(totals)) if totals else to_int(u.get("total_display_price")),
            sqft=to_int(u.get("area")),
            building=u.get("building") or None,
            available_date=parse_date(u.get("available_on"), today),
            lease_months=int(lease.group(1)) if lease else flat_lease,
            specials=[{"title": special[:120], "description": special}] if special else [],
        ))

    text = page_text(page) if page else ""
    extra = page_plan_details(page) if page else {}
    by_plan = defaultdict(list)
    for u in units:
        by_plan[u.floorplan_code].append(u)
    floorplans = []
    for pid, fp in plans_by_id.items():
        name = _plan_name(fp.get("name") or "")
        us = by_plan.get(pid, [])
        if name.upper() == "TEMP" and not us:  # placeholder plan
            continue
        prices = [u.price for u in us if u.price]
        dates = sorted(u.available_date for u in us if u.available_date)
        sqfts = [u.sqft for u in us if u.sqft]
        floorplans.append(FloorPlan(
            code=pid,
            name=name,
            beds=to_float(fp.get("bedroom_count")),
            baths=to_float(fp.get("bathroom_count")),
            sqft=min(sqfts) if sqfts else (sqft_on_page(text, name) or (extra.get(_norm(name)) or (None, None))[0]),
            rent_min=min(prices) if prices else None,
            rent_max=max(prices) if prices else None,
            units_available=len(us),
            earliest_available=dates[0] if dates else None,
            image_url=fp.get("image_url") or (extra.get(_norm(name)) or (None, None))[1],
            lease_months=next((u.lease_months for u in us if u.lease_months), None),
        ))
    return floorplans, units


def scrape(cfg: dict, today: Optional[date] = None) -> Tuple[PropertyInfo, List[FloorPlan], List[Unit]]:
    page = http_get(cfg["url"])
    # Plain link, or JSON-escaped inside page data (Attain: "https:\/\/sightmap.com\/embed\/<id>").
    embed = re.search(r"sightmap\.com\\?/embed\\?/([a-z0-9]{6,})", page)
    if not embed:
        raise ValueError("No SightMap embed on page; site template may have changed")
    embed_page = http_get(f"https://sightmap.com/embed/{embed.group(1)}")
    api = re.search(r"https://sightmap\.com/app/api/v1/[a-z0-9]+/sightmaps/\d+", embed_page)
    if not api:
        raise ValueError("SightMap data URL not found in embed page")
    floorplans, units = parse(json.loads(http_get(api.group(0))), today, page)
    info = parse_property(page)
    if not info.phone and ':property="' in page:  # RealPage/Vest pages (Attain) carry the phone in :property
        try:
            from .realpage_craft import _prop
            prop = _prop(page, "property")
            info.phone = prop.get("phone") or None
            info.address = info.address or prop.get("address")
        except Exception:
            pass
    return info, floorplans, units
