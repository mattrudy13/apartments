from build import apply_specials, build_complex, unit_histories, viable_rows


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


def test_unpriced_complex_and_price_basis():
    s = snap([unit("1", 1), unit("2", 1)])
    for u in s["units"]:
        u["price"] = None  # "Rent: Call"
    s["floorplans"][0]["rent_min"] = None
    s["price_basis"] = "base"
    summary, detail = build_complex({"slug": "t", "name": "Test", "url": "x"}, history(s), {"ok": True})
    assert summary["units"] == 2 and summary["min_price"] is None and summary["priced"] is False
    assert summary["price_basis"] == "base"


def test_total_price_and_total_basis():
    u1, u2 = unit("1", 1800), unit("2", 1900)
    u1["total_price"], u2["total_price"] = 1846, 1946
    s = snap([u1, u2])
    s["price_basis"] = "total"
    summary, detail = build_complex({"slug": "t", "name": "Test", "url": "x"}, history(s), {"ok": True})
    assert summary["min_total"] == 1846 and summary["price_basis"] == "total" and summary["priced"] is True
    assert detail["floorplans"][0]["total_min"] == 1846 and detail["price_basis"] == "total"


def test_old_snapshot_price_basis_comes_from_scraper():
    s = snap([unit("1", 1944)])  # no price_basis key, like snapshots saved before it existed
    summary, detail = build_complex({"slug": "r", "name": "R", "url": "x", "scraper": "entrata"}, history(s), {"ok": True})
    assert summary["price_basis"] == "total" and detail["price_basis"] == "total"


def test_unpriced_units_have_no_price_changes():
    def call_snap():
        s = snap([unit("1", 1)])
        s["units"][0]["price"] = None
        s["floorplans"][0]["rent_min"] = None
        return s
    uh, _ = unit_histories(history(call_snap(), call_snap()))
    assert uh["A#1"]["price_changes"] == 0 and uh["A#1"]["price_change"] == 0


def test_unit_history_since_restarts_unit_tracking():
    h = history(snap([unit("101", 2000, building="4705-WSH")]), snap([unit("101", 2000, building="4705")]))
    cfg = {"slug": "t", "name": "Test", "url": "x", "unit_history_since": "2026-09-27"}
    summary, detail = build_complex(cfg, h, {"ok": True})
    u = detail["units"][0]["history"]
    assert detail["gone_units"] == [] and u["is_new"] is False and detail["history_start"] == "2026-09-27"
    assert len(summary["history"]) == 2  # complex-level price history keeps the older data


def test_total_monthly_with_specials_and_beds():
    u1, u2 = unit("1", 1500, lease=12), unit("2", 1600, lease=12)
    u1["total_price"], u2["total_price"] = 1650, 1700
    s = snap([u1, u2], specials=[{"title": "1 Month Free", "description": ""}], lease=12)
    summary, _ = build_complex({"slug": "t", "name": "T", "url": "x"}, history(s), {"ok": True})
    # $1,500 rent with 1 month free on 12 -> saves $125/mo; net total = 1650 - 125
    assert (summary["min_total"], summary["min_total_net"], summary["total_known"]) == (1650, 1525, 1.0)
    assert summary["by_beds"]["1 BR"]["min_total_net"] == 1525


def test_total_basis_prices_count_as_totals():
    s = snap([unit("1", 1944)])
    summary, _ = build_complex({"slug": "r", "name": "R", "url": "x", "scraper": "entrata"}, history(s), {"ok": True})
    assert summary["min_total"] == 1944 and summary["total_known"] == 1.0


def test_data_checks_flag_self_inconsistency_only():
    a = snap([unit("101", 2000), unit("102", 2100), unit("103", 1500, code="P1")])
    b = snap([unit("101", 2400), unit("102", 2100), unit("103", 1500)])
    b["floorplans"][0]["units_available"] = 5  # plan says 5, only 3 unit rows
    summary, detail = build_complex({"slug": "t", "name": "T", "url": "x"}, history(a, b), {"ok": True})
    text = " | ".join(summary["checks"])
    assert "Plan counts don't match" in text and "#101 $2,000 → $2,400" in text
    assert detail["checks"] == summary["checks"]


def test_data_checks_quiet_for_normal_data():
    # A 2BR cheaper than a 1BR is normal and must not be flagged.
    a = snap([unit("1", 1800), unit("2", 1700)])
    a["floorplans"].append({"code": "P2", "name": "P2", "beds": 2, "rent_min": 1700, "units_available": 0,
                            "earliest_available": None, "lease_months": None, "specials": []})
    summary, _ = build_complex({"slug": "t", "name": "T", "url": "x"}, history(a, a), {"ok": True})
    assert summary["checks"] == []


def test_site_wide_banner_applies_by_beds_and_dedupes():
    banner = {"title": "Move in by Oct 31 and enjoy $500 off 2-bedroom homes or $1,000 off 3-bedroom homes!",
              "description": ""}
    s = snap([unit("101", 1500, lease=12), unit("201", 1800, code="P2", lease=12)])
    s["floorplans"].append({"code": "P2", "name": "P2", "beds": 2, "rent_min": 1800, "units_available": 1,
                            "earliest_available": None, "lease_months": 12, "specials": []})
    s["property_specials"] = [banner]
    summary, detail = build_complex({"slug": "t", "name": "T", "url": "x"}, history(s), {"ok": True})
    one, two = detail["floorplans"]
    assert one["effective_min"] == 1500 and two["effective_min"] == round(1800 - 500 / 12)
    assert two["special_terms"][-1]["site_wide"] and detail["property_special_terms"][0]["beds_off"] == {"2": 500, "3": 1000}
    assert summary["by_beds"]["2 BR"]["min_effective"] == round(1800 - 500 / 12)

    # The same offer listed on a floorplan isn't applied twice.
    s2 = snap([unit("101", 1200, lease=12)], specials=[{"title": "1 Month Free!", "description": ""}], lease=12)
    s2["property_specials"] = [{"title": "1 month free", "description": ""}]
    h = history(s2)
    assert h[0][1]["units"][0]["effective"]["rent"] == 1100 and h[0][1]["property_special_terms"] == []


def test_expired_banner_is_skipped_and_old_snapshots_build():
    s = snap([unit("101", 1820, lease=15)], lease=15)
    s["property_specials"] = [{"title": "Enjoy 2 Weeks Base Rent Free When You Move In by May 31st!", "description": ""}]
    h = history(s)
    e = h[0][1]["units"][0]["effective"]
    assert e["rent"] == 1820 and "has passed" in e["skipped"][0]
    old = history(snap([unit("101", 1200)]))  # no property_specials key at all
    assert old[0][1]["property_special_terms"] == []


# ---------- viable units ----------

CRITERIA = {"beds": [1.0, 2.0], "max_monthly": 1900}


def viable_snap(units, beds=1, basis="base", specials=()):
    s = snap(units, specials=specials)
    s["floorplans"][0]["beds"] = beds
    s["price_basis"] = basis
    return s


def built(s, slug="t"):
    return build_complex({"slug": slug, "name": "Test", "url": "x"}, history(s), {"ok": True}, CRITERIA)


def test_viable_uses_total_with_fees_net_of_specials():
    u1, u2 = unit("1", 1800), unit("2", 1700)
    u1["total_price"], u2["total_price"] = 1950, 1850  # fees push 101 over the limit
    summary, detail = built(viable_snap([u1, u2]))
    assert [(u["monthly"], u["fees_known"], u["viable"]) for u in detail["units"]] == [(1950, True, False), (1850, True, True)]
    assert summary["viable_units"] == 1 and summary["viable_min"] == 1850
    assert detail["floorplans"][0]["viable_units"] == 1


def test_viable_special_brings_total_under():
    special = {"title": "$100 Off Monthly Rent", "description": ""}
    u = unit("1", 1850)
    u["total_price"] = 1950
    _, detail = built(viable_snap([u], specials=[special]))
    assert detail["units"][0]["monthly"] == 1850 and detail["units"][0]["viable"]


def test_viable_total_basis_and_fees_not_listed():
    _, detail = built(viable_snap([unit("1", 1850)], basis="total"))
    assert (detail["units"][0]["monthly"], detail["units"][0]["fees_known"]) == (1850, True)
    _, detail = built(viable_snap([unit("1", 1850)]))  # no fees listed: net rent, flagged
    assert (detail["units"][0]["monthly"], detail["units"][0]["fees_known"], detail["units"][0]["viable"]) == (1850, False, True)


def test_not_viable_studio_3br_call_and_exact_limit():
    assert not built(viable_snap([unit("1", 1500)], beds=0))[1]["units"][0]["viable"]
    assert not built(viable_snap([unit("1", 1500)], beds=3))[1]["units"][0]["viable"]
    assert not built(viable_snap([unit("1", 1900)]))[1]["units"][0]["viable"]  # strictly under
    call = viable_snap([unit("1", 1)])
    call["units"][0]["price"] = None
    assert not built(call)[1]["units"][0]["viable"]


def test_viable_rows_skip_stale_complexes():
    summary, detail = built(viable_snap([unit("1", 1500)]))
    rows = viable_rows(summary, detail)
    assert [(r["unit_number"], r["monthly"], r["plan"]) for r in rows] == [("1", 1500, "P1")]
    assert viable_rows({**summary, "stale": True}, detail) == []


# ---------- lease terms ----------

def termed(price, options, total_fee=None, lease=15):
    """A unit quoted at `price` for `lease` months, with per-term prices {months: price}."""
    u = unit("1", price, lease=lease)
    u["lease_options"] = [{"months": m, "price": p, "total_price": p + total_fee if total_fee else None}
                          for m, p in options.items()]
    if total_fee:
        u["total_price"] = price + total_fee
    return u


def test_cheapest_term_ties_go_shorter_and_short_terms_ignored():
    # ReNew-like: 9-15 months share the low price, 12 costs more; 9 and 10 are under the minimum.
    s = snap([termed(2744, {9: 2700, 10: 2744, 11: 2744, 12: 3244, 15: 2744})])
    s["price_basis"] = "total"
    apply_specials(s, "2026-10-10", min_lease=11)
    u = s["units"][0]
    assert (u["price"], u["lease_months"]) == (2744, 11)
    assert u["quoted"] == {"price": 2744, "total_price": None, "lease_months": 15}
    assert [o["months"] for o in u["lease_options"] if o.get("chosen")] == [11]
    assert [o["allowed"] for o in u["lease_options"]] == [False, False, True, True, True]
    assert not u.get("short_term")


def test_cheapest_term_uses_total_with_fees():
    s = snap([termed(1812, {12: 1861, 13: 1834, 14: 1812}, total_fee=46)])
    apply_specials(s, "2026-10-10", min_lease=11)
    u = s["units"][0]
    assert (u["price"], u["total_price"], u["lease_months"]) == (1812, 1858, 14)
    assert s["floorplans"][0]["rent_min"] == 1812 and s["floorplans"][0]["lease_months"] == 14


def test_special_for_longer_leases_can_change_the_pick():
    # Two months free on 13+ month leases: 13 months at $2,000 nets $1,692, beating 12 at $1,900.
    special = {"title": "Two Months Free", "description": "on 13+ month leases"}
    s = snap([termed(2000, {12: 1900, 13: 2000})], specials=[special])
    apply_specials(s, "2026-10-10", min_lease=11)
    u = s["units"][0]
    assert u["lease_months"] == 13 and u["effective"]["rent"] == 1692
    assert {o["months"]: o["monthly"] for o in u["lease_options"]} == {12: 1900, 13: 1692}


def test_only_short_terms_keeps_quote_and_flags():
    s = snap([termed(2000, {3: 2500, 6: 2300}, lease=6)])
    apply_specials(s, "2026-10-10", min_lease=11)
    u = s["units"][0]
    assert (u["price"], u["lease_months"], u["short_term"]) == (2000, 6, True)
    assert "quoted" not in u
    # Single quotes under the minimum (Salt Meadow's 9-month cards) are flagged too; unknown terms aren't.
    s = snap([unit("1", 1800, lease=9), unit("2", 1800, lease=None), unit("3", 1800, lease=12)])
    apply_specials(s, "2026-10-10", min_lease=11)
    assert [u["short_term"] for u in s["units"]] == [True, False, False]


def test_no_minimum_uses_every_term_and_old_snapshots_unchanged():
    s = snap([termed(2135, {6: 2100, 13: 2135, 15: 2135})])
    apply_specials(s, "2026-10-10")
    assert s["units"][0]["lease_months"] == 6
    s = snap([unit("1", 1800, lease=15)])  # no lease_options: nothing picked
    apply_specials(s, "2026-10-10", min_lease=11)
    assert (s["units"][0]["price"], s["units"][0]["lease_months"]) == (1800, 15) and "quoted" not in s["units"][0]


def test_picked_term_drives_viable():
    u = termed(1950, {12: 1950, 14: 1880}, lease=12)
    s = viable_snap([u])
    apply_specials(s, "2026-10-10", min_lease=11)
    summary, detail = build_complex({"slug": "t", "name": "Test", "url": "x", "scraper": "sightmap"},
                                    [("2026-10-10", s)], {"ok": True}, CRITERIA)
    assert detail["units"][0]["viable"] and detail["units"][0]["monthly"] == 1880
    assert summary["source"] == "SightMap (live unit map)"


def test_lows_cover_the_window_and_start_at_unit_history_since():
    # 09-20 had a bogus low from an old source; 09-27 is the real low; it has risen since.
    h = history(snap([unit("1", 1200)]), snap([unit("1", 1500)]), snap([unit("1", 1600)]), snap([unit("1", 1700)]))
    cfg = {"slug": "t", "name": "T", "url": "x", "unit_history_since": "2026-09-27"}
    summary, detail = build_complex(cfg, h, {"ok": True})
    assert summary["lows"]["1 BR"]["min_price"] == 1500
    assert detail["floorplans"][0]["low"]["rent_min"] == 1500
    summary, _ = build_complex({"slug": "t", "name": "T", "url": "x"}, h, {"ok": True})
    assert summary["lows"]["1 BR"]["min_price"] == 1200


def test_lows_skip_pulls_older_than_90_days():
    old, new = snap([unit("1", 1000)]), snap([unit("1", 1500)])
    apply_specials(old, "2026-06-01")
    apply_specials(new, "2026-10-11")
    summary, _ = build_complex({"slug": "t", "name": "T", "url": "x"}, [("2026-06-01", old), ("2026-10-11", new)], {"ok": True})
    assert summary["lows"]["1 BR"]["min_price"] == 1500


def test_latest_move_in_ignores_undated_units():
    s = snap([unit("1", 1500, avail="2026-11-01"), unit("2", 1600, avail="2027-01-15"), unit("3", 1700, avail=None)])
    summary, _ = build_complex({"slug": "t", "name": "T", "url": "x"}, history(s), {"ok": True})
    assert summary["latest_move_in"] == "2027-01-15"
    summary, _ = build_complex({"slug": "t", "name": "T", "url": "x"}, history(snap([unit("1", 1500, avail=None)])), {"ok": True})
    assert summary["latest_move_in"] is None
