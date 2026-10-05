from datetime import date
from pathlib import Path

from scraper import entrata, realpage_craft
from scraper.fetch import parse_date

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 4)


def read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_realpage_craft_attain():
    info, floorplans, units = realpage_craft.parse(read("attain.html"), TODAY)
    assert info.address == "4705 Windsong Dr, Virginia Beach, VA, 23455"
    assert len(floorplans) == 49
    assert sum(fp.units_available for fp in floorplans) == 29
    assert len(units) == 29  # only available units are kept

    b30e = next(fp for fp in floorplans if fp.code == "B30E")
    assert (b30e.beds, b30e.baths, b30e.sqft, b30e.rent_min, b30e.units_available) == (2, 2, 1055, 2167, 2)

    codes = {fp.code for fp in floorplans}
    assert all(u.floorplan_code in codes for u in units)
    assert all(u.price and u.available_date for u in units)


def test_entrata_floorplans_listing():
    plans = entrata.parse_floorplans(read("renew_floorplans.html"), TODAY)
    assert [p.name for p in plans] == [
        "Arlington", "Athens", "Arlington Loft", "Baltimore", "Chesapeake", "Chesapeake Loft", "Dover", "Douglas",
    ]

    by_name = {p.name: p for p in plans}
    arlington = by_name["Arlington"]
    assert arlington.units_available == 0 and arlington.rent_min is None
    assert [sp["title"] for sp in arlington.specials] == ["Two Months Free"]
    assert "12+ month lease terms" in arlington.specials[0]["description"]

    athens = by_name["Athens"]
    assert (athens.code, athens.beds, athens.baths, athens.sqft) == ("690916", 1, 1, 730)
    assert (athens.rent_min, athens.rent_max) == (1944, 2364)
    assert athens.earliest_available == "2026-11-17"
    assert athens.lease_months == 15

    douglas = by_name["Douglas"]
    assert (douglas.beds, douglas.units_available, douglas.rent_min) == (3, 3, 2794)
    assert douglas.details_url.endswith("/floorplans/douglas-690926/fp_name/occupancy_type/conventional/")


def test_entrata_units_detail():
    units = entrata.parse_units(read("renew_detail_douglas.html"), "690926", TODAY)
    assert [(u.unit_number, u.building, u.price, u.sqft, u.available_date) for u in units] == [
        ("207", "2221", 2794, 1316, "2026-10-04"),
        ("208", "2205", 2794, 1316, "2026-10-04"),
        ("206", "2261", 2814, 1316, "2026-10-04"),
    ]
    assert all(u.lease_months == 15 for u in units)


def test_entrata_property_info():
    info = entrata.parse_property(read("renew_floorplans.html"))
    assert info.address == "2257 Willow Oak Cir., Virginia Beach, 23451"
    assert info.phone == "866-203-4610"


def test_parse_date():
    assert parse_date("09/25/2026") == "2026-09-25"
    assert parse_date("Nov 17, 2026") == "2026-11-17"
    assert parse_date("Now", TODAY) == "2026-10-04"
    assert parse_date("12/31/0000") is None
    assert parse_date("") is None
