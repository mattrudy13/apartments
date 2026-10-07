"""Normalized schema shared by every scraper. Snapshots are written as JSON."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class FloorPlan:
    code: str
    name: str
    beds: Optional[float] = None
    baths: Optional[float] = None
    sqft: Optional[int] = None
    rent_min: Optional[int] = None
    rent_max: Optional[int] = None
    units_available: int = 0
    earliest_available: Optional[str] = None  # ISO date
    image_url: Optional[str] = None
    details_url: Optional[str] = None
    lease_months: Optional[int] = None  # lease term the listed price is quoted for, if shown
    specials: List[Dict[str, str]] = field(default_factory=list)  # [{title, description}]


@dataclass
class Unit:
    unit_number: str
    floorplan_code: str
    price: Optional[int] = None
    sqft: Optional[int] = None
    floor: Optional[str] = None
    building: Optional[str] = None
    available_date: Optional[str] = None  # ISO date; on/before scrape date means "now"
    apply_url: Optional[str] = None
    total_price: Optional[int] = None  # base rent + required monthly fees, when the site shows it
    lease_months: Optional[int] = None
    specials: List[Dict[str, str]] = field(default_factory=list)  # unit-specific specials


@dataclass
class PropertyInfo:
    address: Optional[str] = None
    phone: Optional[str] = None


@dataclass
class Snapshot:
    slug: str
    name: str
    url: str
    scraped_at: str  # ISO datetime, UTC
    property: PropertyInfo
    floorplans: List[FloorPlan]
    units: List[Unit]
    # "base": `price` is base rent (default). "total": the site only shows a total that
    # already includes required monthly fees (e.g. Entrata's "Total Monthly Leasing Price").
    price_basis: str = "base"
    # Specials from a site-wide banner (complexes.yaml `banner:`), applied to every floorplan at build.
    property_specials: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
