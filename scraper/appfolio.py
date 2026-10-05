"""AppFolio listings on Duda-built property sites (e.g. northbeachvbliving.com).

The availability page's listings widget loads JSON from the site's own collection API:
  /rts/collections/public/<siteAlias>/runtime/collection/appfolio-listings/query-data
<siteAlias> appears in the page HTML. The collection holds every listing in the
management company's AppFolio account (several properties), so it's filtered to this
site by `portfolio_url`. Each listing is one unit; floorplans are grouped from
`unit_template_name`. Plain HTTP works.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from .fetch import http_get, parse_date, to_float, to_int
from .models import FloorPlan, PropertyInfo, Unit

QUERY = "/rts/collections/public/{alias}/runtime/collection/appfolio-listings/query-data?pageSize=100&pageNumber={page}&query=%28%29&language=ENGLISH"


def _host(url: str) -> str:
    return re.sub(r"^www\.", "", urlparse(url).netloc.lower())


def listings_for_site(listings: List[dict], site_url: str) -> List[dict]:
    host = _host(site_url)
    return [x for x in listings if x.get("portfolio_url") and _host(x["portfolio_url"]) == host]


def parse(listings: List[dict], today: Optional[date] = None) -> Tuple[PropertyInfo, List[FloorPlan], List[Unit]]:
    if not listings:
        raise ValueError("No AppFolio listings for this site")
    units = []
    for x in listings:
        if not x.get("available", True):
            continue
        rent = x.get("market_rent") or (x.get("rent_range") or [None])[0]
        lease = to_int(x.get("advertised_lease_term"))
        units.append(Unit(
            unit_number=(x.get("address_address2") or "").lstrip("#").strip() or x["full_address"],
            floorplan_code=x.get("unit_template_name") or x.get("marketing_title") or "Unit",
            price=to_int(rent),
            sqft=to_int(x.get("square_feet")),
            building=(x.get("address_address1") or "").strip() or None,
            available_date=parse_date(x.get("available_date"), today),
            apply_url=x.get("rental_application_url"),
            lease_months=lease if lease and lease <= 36 else None,
        ))

    meta = {}
    by_plan = defaultdict(list)
    for x in listings:
        plan = x.get("unit_template_name") or x.get("marketing_title") or "Unit"
        meta.setdefault(plan, x)
    for u in units:
        by_plan[u.floorplan_code].append(u)
    floorplans = []
    for plan, x in meta.items():
        us = by_plan.get(plan, [])
        prices = [u.price for u in us if u.price]
        dates = sorted(u.available_date for u in us if u.available_date)
        photo = x.get("default_photo_thumbnail_url") or ((x.get("photos") or [{}])[0].get("url"))
        floorplans.append(FloorPlan(
            code=plan,
            name=plan,
            beds=to_float(x.get("bedrooms")),
            baths=to_float(x.get("bathrooms")),
            sqft=to_int(x.get("square_feet")),
            rent_min=min(prices) if prices else None,
            rent_max=max(prices) if prices else None,
            units_available=len(us),
            earliest_available=dates[0] if dates else None,
            image_url=photo,
        ))

    first = listings[0]
    phone = first.get("portfolio_phone_number") or first.get("contact_phone_number")
    parts = [first.get("portfolio_address1"), first.get("portfolio_city"), first.get("portfolio_state"), first.get("portfolio_postal_code")]
    info = PropertyInfo(address=", ".join(p for p in parts if p) or None, phone=phone)
    return info, floorplans, units


def scrape(cfg: dict, today: Optional[date] = None):
    page = http_get(cfg["url"])
    m = re.search(r"siteAlias\s*=\s*['\"]([a-z0-9]+)['\"]", page)
    if not m:
        raise ValueError("siteAlias not found on page; site template may have changed")
    base = f"{urlparse(cfg['url']).scheme}://{urlparse(cfg['url']).netloc}"
    listings, page_no = [], 0
    while True:
        data = json.loads(http_get(base + QUERY.format(alias=m.group(1), page=page_no)))
        listings += [v["data"] for v in data.get("values", [])]
        page_no += 1
        if page_no >= (data.get("page") or {}).get("totalPages", 1):
            break
    return parse(listings_for_site(listings, cfg.get("website") or cfg["url"]), today)
