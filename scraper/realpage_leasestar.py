"""RealPage LeaseStar sites (e.g. livenorthhillapts.com, a Greystar site).

The floor-plans page loads its data from `api.ws.realpage.com/v2/property/<id>/floorplans`
and `/units?available=true...`. The API rejects requests without a token the page's own
JavaScript obtains (401), so the page is loaded in Chrome and those JSON responses are
read as they arrive.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import List, Optional, Tuple

from .entrata import parse_property
from .fetch import Browser, parse_date, to_float, to_int
from .models import FloorPlan, PropertyInfo, Unit

FLOORPLANS = "/floorplans"
UNITS = "/units?available=true"


def _date(text: Optional[str], today: Optional[date]) -> Optional[str]:
    """'2026-10-08 00:00 -0000' -> '2026-10-08'."""
    return parse_date((text or "")[:10], today) if text else None


def parse(floorplans_json: dict, units_json: dict, today: Optional[date] = None) -> Tuple[List[FloorPlan], List[Unit]]:
    raw_plans = (floorplans_json.get("response") or {}).get("floorplans") or []
    raw_units = (units_json.get("response") or {}).get("units") or []

    units, beds_by_plan = [], {}
    for u in raw_units:
        if not u.get("displayed", True) or u.get("unitLeasedStatus", "Available") != "Available":
            continue
        code = str(u.get("floorplanId"))
        beds_by_plan.setdefault(code, to_float(u.get("numberOfBeds")))
        total = to_float(u.get("totalRent"))
        units.append(Unit(
            unit_number=str(u.get("unitNumber") or u.get("name")),
            floorplan_code=code,
            price=to_int(u.get("rent")),
            total_price=round(total) if total else None,
            sqft=to_int(u.get("squareFeet")),
            floor=str(u["floorNumber"]) if u.get("floorNumber") else None,
            available_date=_date(u.get("vacantDate") or u.get("internalAvailableDate"), today),
            lease_months=to_int(u.get("minLeaseTermInMonth")),
        ))

    by_plan = defaultdict(list)
    for u in units:
        by_plan[u.floorplan_code].append(u)
    # Plan-level bed counts have been wrong (plan B2 listed as 1 bed; its units are 2-bed, and
    # the property is all 2-bedroom). If any plan's units contradict its own count, fall back
    # to the most common unit bed count for plans that have no units.
    plan_beds = {str(fp.get("id")): to_float(fp.get("bedRooms")) for fp in raw_plans}
    unit_beds = [b for b in beds_by_plan.values() if b is not None]
    contradicted = any(plan_beds.get(c) != b for c, b in beds_by_plan.items() if b is not None)
    fallback_beds = max(set(unit_beds), key=unit_beds.count) if contradicted and unit_beds else None
    plans = []
    for fp in raw_plans:
        code = str(fp.get("id"))
        us = by_plan.get(code, [])
        prices = [u.price for u in us if u.price]
        dates = sorted(u.available_date for u in us if u.available_date)
        special = (fp.get("specials") or "").strip() if isinstance(fp.get("specials"), str) else ""
        image = (fp.get("diagramUrl") or "").replace("%s", "400x400") or None
        plans.append(FloorPlan(
            code=code,
            name=fp.get("name") or code,
            beds=beds_by_plan.get(code, fallback_beds if fallback_beds is not None else plan_beds.get(code)),
            baths=to_float(fp.get("bathRooms")),
            sqft=to_int(fp.get("minimumSquareFeet")),
            rent_min=min(prices) if prices else None,
            rent_max=max(prices) if prices else None,
            units_available=len(us),
            earliest_available=dates[0] if dates else None,
            image_url=image,
            lease_months=next((u.lease_months for u in us if u.lease_months), None),
            specials=[{"title": special[:120], "description": special}] if special else [],
        ))
    return plans, units


def scrape(cfg: dict, today: Optional[date] = None) -> Tuple[PropertyInfo, List[FloorPlan], List[Unit]]:
    with Browser() as browser:
        data = browser.get_json_responses(cfg["url"], [FLOORPLANS, UNITS])
        page = browser._page.content()
    floorplans, units = parse(data[FLOORPLANS], data[UNITS], today)
    return parse_property(page), floorplans, units
