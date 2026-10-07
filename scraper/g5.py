"""G5 Marketing Cloud sites (e.g. columbusstationapartments.com).

The floor-plans page renders from G5's inventory GraphQL API, which needs no auth:
an `apartmentComplex(locationUrn)` query lists floorplans with available counts and rate
ranges, and a `units(floorplanId)` query per floorplan lists its units. The location URN
(`g5-cl-...`) is in the page HTML. Plain HTTP works. The queries below are trimmed copies
of the ones the site sends, keeping only the fields we use.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from typing import List, Optional, Tuple

import httpx

from .entrata import parse_property
from .fetch import USER_AGENT, http_get, parse_date, to_float, to_int
from .models import FloorPlan, PropertyInfo, Unit

API = "https://inventory.g5marketingcloud.com/graphql"
UNITS_LIMIT = 100  # the site asks for 9; ask for all

COMPLEX_QUERY = """query ApartmentComplex($locationUrn: String!, $moveInDate: String!) {
  apartmentComplex(locationUrn: $locationUrn) {
    id
    hasApartmentSpecials
    floorplans(moveInDate: $moveInDate) {
      id name totalAvailableUnits beds baths sqft startingRate endingRate imageUrl
      leaseTermBasisMin hasSpecials
      floorplanSpecials { id name }
    }
  }
}"""

UNITS_QUERY = """query Units($limit: Int, $moveInDate: String, $locationUrn: String) {
  units(floorplanId: %d, limit: $limit, moveInDate: $moveInDate, locationUrn: $locationUrn) {
    name displayName building availabilityDate sqftDisplay
    prices { priceType value leaseTermBasisMin }
    callToActions { name url }
  }
}"""


def _post(query: str, variables: dict, origin: str) -> dict:
    resp = httpx.post(API, json={"query": query, "variables": variables},
                      headers={"User-Agent": USER_AGENT, "Origin": origin}, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        raise ValueError(f"G5 GraphQL error: {body['errors'][0].get('message')}")
    return body["data"]


def location_urn(page: str) -> str:
    urns = Counter(re.findall(r"g5-cl-[a-z0-9-]+", page))
    if not urns:
        raise ValueError("No G5 location URN (g5-cl-...) on page; site template may have changed")
    return urns.most_common(1)[0][0]


def parse(complex_data: dict, units_by_plan: dict, today: Optional[date] = None) -> Tuple[List[FloorPlan], List[Unit]]:
    plans, units = [], []
    for fp in (complex_data.get("apartmentComplex") or {}).get("floorplans") or []:
        code = str(fp["id"])
        raw_units = (units_by_plan.get(code) or {}).get("units") or []
        fp_units = []
        for u in raw_units:
            rates = [to_float(p.get("value")) for p in u.get("prices") or [] if p.get("value")]
            apply = next((c.get("url") for c in u.get("callToActions") or []
                          if (c.get("url") or "").startswith("http") and "apply" in (c.get("name") or "").lower()), None)
            if apply:  # drop the widget's search-state tail ("&SearchUrl=...{widget.moveInDate...}")
                apply = apply.split("&SearchUrl=")[0].strip()
            building = u.get("building")
            fp_units.append(Unit(
                unit_number=u.get("displayName") or u.get("name"),
                floorplan_code=code,
                price=round(min(rates)) if rates else None,
                sqft=to_int(u.get("sqftDisplay")) or to_int(fp.get("sqft")),
                building=None if building in (None, "", "N/A") else building,
                available_date=parse_date(u.get("availabilityDate"), today),
                apply_url=apply,
            ))
        count = len(fp_units) or int(fp.get("totalAvailableUnits") or 0)
        prices = [u.price for u in fp_units if u.price]
        dates = sorted(u.available_date for u in fp_units if u.available_date)
        specials = [{"title": s["name"], "description": ""} for s in fp.get("floorplanSpecials") or [] if s.get("name")]
        plans.append(FloorPlan(
            code=code,
            name=fp.get("name") or code,
            beds=to_float(fp.get("beds")),
            baths=to_float(fp.get("baths")),
            sqft=to_int(fp.get("sqft")),
            rent_min=(min(prices) if prices else to_int(fp.get("startingRate"))) if count else None,
            rent_max=(max(prices) if prices else to_int(fp.get("endingRate"))) if count else None,
            units_available=count,
            earliest_available=dates[0] if dates else None,
            image_url=fp.get("imageUrl"),
            lease_months=to_int(fp.get("leaseTermBasisMin")),
            specials=specials,
        ))
        units.extend(fp_units)
    return plans, units


def scrape(cfg: dict, today: Optional[date] = None) -> Tuple[PropertyInfo, List[FloorPlan], List[Unit]]:
    page = http_get(cfg["url"])
    urn = location_urn(page)
    origin = re.match(r"https?://[^/]+", cfg["url"]).group(0)
    complex_data = _post(COMPLEX_QUERY, {"locationUrn": urn, "moveInDate": ""}, origin)
    units_by_plan = {}
    for fp in complex_data["apartmentComplex"]["floorplans"]:
        if fp.get("totalAvailableUnits"):
            units_by_plan[str(fp["id"])] = _post(
                UNITS_QUERY % int(fp["id"]), {"limit": UNITS_LIMIT, "moveInDate": "", "locationUrn": urn}, origin)
    floorplans, units = parse(complex_data, units_by_plan, today)
    return parse_property(page), floorplans, units
