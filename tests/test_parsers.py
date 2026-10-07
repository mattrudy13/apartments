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


def test_sightmap_nexus():
    import json

    from scraper import sightmap

    plans, units = sightmap.parse(json.loads(read("sightmap_nexus_api.json")), TODAY, read("sightmap_nexus_floorplans.html"))
    assert [p.name for p in plans] == ["A0", "A1", "A2", "A3", "B1", "B2", "B3", "E1"]  # TEMP placeholder dropped
    assert len(units) == 9 and sum(p.units_available for p in plans) == 9
    u = units[0]
    assert (u.unit_number, u.building, u.price, u.total_price, u.sqft, u.available_date, u.lease_months) == (
        "546-130", "546", 1824, 1870, 563, "2026-10-19", 14)
    e1 = next(p for p in plans if p.name == "E1")
    assert (e1.beds, e1.rent_min, e1.units_available) == (0, 1824, 1)  # studio
    assert next(p for p in plans if p.name == "B2").sqft == 1239  # from the page; SightMap has no plan sqft
    assert entrata.parse_property(read("sightmap_nexus_floorplans.html")).phone == "757-663-5564"  # @graph JSON-LD


def test_realpage_leasestar_north_hill():
    import json

    from scraper import realpage_leasestar

    data = json.loads(read("realpage_northhill_api.json"))
    plans, units = realpage_leasestar.parse(data["floorplans"], data["units"], TODAY)
    assert len(plans) == 9 and len(units) == 6
    u = units[0]
    assert (u.unit_number, u.price, u.total_price, u.sqft, u.floor, u.available_date, u.lease_months) == (
        "613-201", 1820, 1846, 846, "2", "2026-10-08", 15)
    # Plan B2 claims 1 bed but its units are 2-bed; plans without units fall back to the unit majority.
    assert {p.beds for p in plans} == {2}
    b2 = next(p for p in plans if p.name == "B2")
    assert (b2.rent_min, b2.units_available) == (1820, 3)


def test_g5_columbus_station():
    import json

    from scraper import g5

    assert g5.location_urn(read("g5_columbus_floorplans.html")) == "g5-cl-1o802dwcee-dragas-companies-virginia-beach-va"
    data = json.loads(read("g5_columbus_graphql.json"))
    plans, units = g5.parse(data["complex"]["data"], {k: v["data"] for k, v in data["units"].items()}, TODAY)
    assert len(plans) == 8 and len(units) == 23 and sum(p.units_available for p in plans) == 23
    tierra = next(p for p in plans if p.name == "Tierra (Not Pet Friendly)")
    assert (tierra.beds, tierra.sqft, tierra.rent_min, tierra.units_available) == (1, 675, 1745, 1)
    santa = next(p for p in plans if p.name.startswith("Santa Maria"))
    assert (santa.units_available, santa.rent_min) == (0, None)  # rate range shown, but nothing available
    u = next(x for x in units if x.unit_number == "117I302")
    assert (u.price, u.sqft, u.available_date, u.building) == (1745, 675, "2026-11-25", None)
    assert u.apply_url.endswith("apply?siteId=3921390&unitId=132")  # widget tail trimmed
    assert entrata.parse_property(read("g5_columbus_floorplans.html")).address == "4516 Pinta Ln, Virginia Beach, VA, 23462"


def test_rentcafe_indigo_no_prices():
    from scraper import rentcafe

    plans = rentcafe.parse_floorplans(read("rentcafe_indigo_floorplans.html"), "https://www.indigo19apartments.com/floorplans", TODAY)
    assert len(plans) == 8 and sum(p.units_available for p in plans) == 13
    largo = next(p for p in plans if p.name == "Largo")
    # "Call for Details" cards have no plan link; the URL is derived from the name.
    assert (largo.rent_min, largo.units_available, largo.details_url) == (
        None, 7, "https://www.indigo19apartments.com/floorplans/largo")
    units = rentcafe.parse_units(read("rentcafe_indigo_largo.html"), largo.code, TODAY)
    assert len(units) == 7 and all(u.price is None for u in units)
    assert (units[0].unit_number, units[0].sqft) == ("1-327", 1082)


def test_rentcafe_card_layout_salt_meadow():
    from scraper import rentcafe

    plans = rentcafe.parse_floorplans(read("rentcafe_saltmeadow_floorplans.html"), "https://www.saltmeadowbay.com/floorplans", TODAY)
    assert len(plans) == 16
    egret = next(p for p in plans if p.name == "Egret")
    assert (egret.beds, egret.baths, egret.sqft) == (2, 2, 1213)
    units = rentcafe.parse_units(read("rentcafe_saltmeadow_egret.html"), egret.code, TODAY)
    assert len(units) == 9
    u = next(x for x in units if x.unit_number == "0837-210")
    # "Total Monthly Leasing Price Starting at $2,373" + "Base rent $2,333 · 9-month term"
    assert (u.price, u.total_price, u.lease_months, u.available_date) == (2333, 2373, 9, TODAY.isoformat())  # "Now"
    assert next(x for x in units if x.unit_number == "0837-116").available_date == "2026-11-02"  # "Date Available:"
    plain = next(x for x in units if x.unit_number == "0817-113")  # no fee breakdown: "Starting at" is the rent
    assert (plain.price, plain.total_price) == (2416, None)
