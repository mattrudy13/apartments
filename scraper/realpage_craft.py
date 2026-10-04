"""RealPage / Vest Residential sites (e.g. attainchicsbeach.com).

The page embeds its data as Vue props: :property="{...}", :floorplans="[...]",
:units="[...]" (HTML-escaped JSON), so no browser is needed.
"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from typing import List, Optional, Tuple

from .fetch import http_get, parse_date, to_float, to_int
from .models import FloorPlan, PropertyInfo, Unit


def _prop(page: str, name: str):
    m = re.search(r'\s:%s="([^"]*)"' % re.escape(name), page)
    if not m:
        raise ValueError(f"':{name}' data not found on page; site template may have changed")
    return json.loads(html.unescape(m.group(1)))


def parse(page: str, today: Optional[date] = None) -> Tuple[PropertyInfo, List[FloorPlan], List[Unit]]:
    prop = _prop(page, "property")
    raw_fps = _prop(page, "floorplans")
    raw_units = _prop(page, "units")

    units = [
        Unit(
            unit_number=str(u["unitNumber"]),
            floorplan_code=u.get("floorPlanCode") or "",
            price=to_int(u.get("unitPrice")),
            sqft=to_int(u.get("unitInteriorSquareFeet")),
            floor=u.get("unitFloor"),
            building=u.get("buildingNumber") or u.get("buildingName"),
            available_date=parse_date(u.get("unitAvailableDate"), today),
            apply_url=u.get("unitApplicationLink"),
        )
        for u in raw_units
        if u.get("unitAvailable")
    ]

    floorplans = [
        FloorPlan(
            code=f["floorPlanCode"],
            name=f.get("floorPlanName") or f["floorPlanCode"],
            beds=to_float(f.get("floorPlanBedrooms")),
            baths=to_float(f.get("floorPlanBathrooms")),
            sqft=to_int(f.get("floorPlanInteriorSquareFeet")),
            rent_min=to_int(f.get("floorPlanRentMin")),
            rent_max=to_int(f.get("floorPlanRentMax")),
            units_available=int(f.get("numberUnitsAvailable") or 0),
            earliest_available=parse_date(f.get("floorPlanEarliestAvailableDate"), today),
            image_url=f.get("floorPlanImageFull") or f.get("floorPlanImage"),
            specials=["Special available"] if f.get("floorPlanHasSpecials") else [],
        )
        for f in raw_fps
    ]

    info = PropertyInfo(address=prop.get("address"), phone=prop.get("phone"))
    return info, floorplans, units


def scrape(cfg: dict, today: Optional[date] = None):
    return parse(http_get(cfg["url"]), today)
