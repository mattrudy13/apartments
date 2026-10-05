from build import apply_specials, build_complex, unit_histories


def unit(num, price, building="A", code="P1", avail="2026-10-01", lease=None):
    return {"unit_number": num, "building": building, "floorplan_code": code, "price": price,
            "available_date": avail, "lease_months": lease, "specials": []}


def snap(units, specials=(), lease=None):
    return {
        "name": "Test", "url": "https://example.com", "property": {"address": None},
        "floorplans": [{"code": "P1", "name": "P1", "beds": 1, "rent_min": min((u["price"] for u in units), default=None),
                        "units_available": len(units), "earliest_available": None, "lease_months": lease,
                        "specials": list(specials)}],
        "units": units,
    }


def history(*snaps):
    dates = ["2026-09-20", "2026-09-27", "2026-10-04", "2026-10-11"]
    out = []
    for d, s in zip(dates, snaps):
        apply_specials(s, d)
        out.append((d, s))
    return out


def test_unit_history_streaks_price_changes_and_gone():
    h = history(
        snap([unit("101", 2000), unit("102", 2100)]),
        snap([unit("101", 1950), unit("102", 2100)]),
        snap([unit("101", 1900), unit("103", 2200)]),
    )
    uh, gone = unit_histories(h)
    assert uh["A#101"]["first_seen"] == "2026-09-20" and uh["A#101"]["days_listed"] == 14
    assert uh["A#101"]["price_change"] == -100 and uh["A#101"]["price_changes"] == 2
    assert uh["A#103"]["is_new"] and uh["A#103"]["days_listed"] == 0
    assert "A#102" not in uh
    assert gone == [{"unit_number": "102", "building": "A", "floorplan_code": "P1", "last_price": 2100,
                     "last_seen": "2026-09-27"}]


def test_relisted_unit_starts_new_streak():
    h = history(snap([unit("101", 2000)]), snap([unit("102", 2000)]), snap([unit("101", 2050)]))
    uh, _ = unit_histories(h)
    assert uh["A#101"]["first_seen"] == "2026-10-04" and uh["A#101"]["price_changes"] == 0


def test_same_unit_number_in_two_buildings_is_two_units():
    uh, _ = unit_histories(history(snap([unit("110", 1944, "2200"), unit("110", 1944, "2208")])))
    assert set(uh) == {"2200#110", "2208#110"}


def test_effective_rent_flows_into_summary():
    special = {"title": "Two Months Free", "description": "Offer valid on 12+ month lease terms."}
    h = history(snap([unit("101", 1500, lease=15), unit("102", 1600, lease=15)], specials=[special], lease=15))
    summary, detail = build_complex({"slug": "t", "name": "Test", "url": "x"}, h, {"ok": True})
    assert summary["min_price"] == 1500 and summary["min_effective"] == 1300
    u = detail["units"][0]
    assert u["effective"]["rent"] == 1300 and u["effective"]["lease_months"] == 15
    assert detail["floorplans"][0]["effective_min"] == 1300


def test_old_snapshot_string_specials_and_assumed_lease():
    h = history(snap([unit("101", 1200)], specials=["1 Month Free"]))
    u = h[0][1]["units"][0]
    assert u["effective"]["rent"] == 1100 and u["effective"]["lease_assumed"]
