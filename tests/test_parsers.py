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


def test_rentcafe_floorplans_listing():
    from scraper import rentcafe

    page = read("rentcafe_floorplans.html")
    plans = rentcafe.parse_floorplans(page, "https://www.linkhornbayapartments-prg.com/floorplans", TODAY)
    assert [p.name for p in plans] == ["The Ash", "The Birch", "The Elm", "The Willow", "The Pine", "The Spruce"]
    birch = plans[1]
    assert (birch.code, birch.beds, birch.baths, birch.sqft, birch.rent_min, birch.units_available) == (
        "602897", 1, 1, 670, 1642, 6)
    assert birch.details_url == "https://www.linkhornbayapartments-prg.com/floorplans/the-birch"
    info = entrata.parse_property(page)  # JSON-LD with @type as a list
    assert info.address == "1201 Waterfront Drive, Virginia Beach, VA, 23451" and info.phone == "757-982-3477"


def test_rentcafe_units_detail():
    from scraper import rentcafe

    units = rentcafe.parse_units(read("rentcafe_detail_birch.html"), "602897", TODAY)
    assert [(u.unit_number, u.price, u.sqft, u.floor, u.available_date) for u in units] == [
        ("502S12", 1672, 670, "1", "2026-10-16"),
        ("502P22", 1667, 670, "2", "2026-10-28"),
        ("502S22", 1642, 670, "2", "2026-10-31"),
        ("500S22", 1657, 670, "2", "2026-11-02"),
        ("514P22", 1697, 670, "2", "2026-11-06"),
        ("502S21", 1642, 670, "2", "2026-11-11"),
    ]
    assert units[0].apply_url.startswith("https://linkhornbayapartments.securecafe.com/")


def test_appfolio_filters_to_site_and_groups_floorplans():
    import json

    from scraper import appfolio

    data = json.loads(read("appfolio_listings.json"))
    listings = [v["data"] for v in data["values"]]
    assert len(listings) == 88  # whole management-company account
    mine = appfolio.listings_for_site(listings, "https://www.northbeachvbliving.com/")
    assert len(mine) == 24
    info, plans, units = appfolio.parse(mine, TODAY)
    assert info.phone == "(757) 460-4781"
    assert len(units) == 24 and sum(p.units_available for p in plans) == 24
    bay = next(p for p in plans if p.code == "Bay (Renovated)")
    assert (bay.beds, bay.baths, bay.sqft, bay.rent_min, bay.units_available) == (2, 1, 875, 2079, 11)
    u = units[0]
    assert (u.unit_number, u.building, u.price, u.available_date) == ("101", "4600 Downeast Court", 2079, "2026-10-25")
    # Same unit number in different buildings stays distinct.
    assert len({(x.building, x.unit_number) for x in units}) == 24
