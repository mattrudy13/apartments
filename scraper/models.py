"""Normalized schema shared by every scraper. Snapshots are written as JSON."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional


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
    specials: List[str] = field(default_factory=list)


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

    def to_dict(self) -> dict:
        return asdict(self)
