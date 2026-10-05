from datetime import date

import pytest

from scraper.specials import effective_rent, parse_special

REF = date(2026, 10, 4)


def p(title, desc=""):
    return parse_special(title, desc, REF)


# ---------- parsing ----------

def test_renew_live_special():
    t = p("Two Months Free", "Enjoy two months FREE when you make ReNew Marina Shores. your new home! "
          "Offer valid on 12+ month lease terms. Please see a Leasing Consultant for details and restrictions.")
    assert t.parsed and t.months_free == 2 and t.min_lease_months == 12
    assert t.move_in_by is None and t.expires is None


@pytest.mark.parametrize("title,months", [
    ("1 Month Free", 1), ("One month free!", 1), ("Get 6 weeks free", round(6 * 7 / (365 / 12), 3)),
    ("Half a month free", 0.5), ("1/2 month free", 0.5), ("First month's rent free", 1),
    ("Free rent for 2 months", 2), ("Up to 8 Weeks Free", round(8 * 7 / (365 / 12), 3)),
])
def test_months_free(title, months):
    t = p(title)
    assert t.parsed and t.months_free == months


def test_dollars_off_one_time_vs_monthly():
    assert (p("$500 off move-in").one_time_off, p("$500 off move-in").monthly_off) == (500, 0)
    t = p("$1,000 off your first month")
    assert t.one_time_off == 1000
    t = p("Save $100 off per month on 2 bedrooms")
    assert (t.one_time_off, t.monthly_off) == (0, 100)


@pytest.mark.parametrize("text,expected", [
    ("Move in by Nov 30 and get 1 month free", "2026-11-30"),
    ("1 month free with move-in by 11/30/2026", "2026-11-30"),
    ("6 weeks free when you move in on or before December 15th", "2026-12-15"),
    ("2 months free if you move in before December 1", "2026-11-30"),  # "before" excludes the date
    ("One month free, move-in by Jan 15", "2027-01-15"),  # no year, already past -> next year
    ("Half month free, move in no later than 10/31", "2026-10-31"),
    ("1 month free with move-in by 2026-11-30", "2026-11-30"),
])
def test_move_in_by(text, expected):
    t = p(text)
    assert t.parsed and t.move_in_by == expected
    assert any("move in by" in c for c in t.caveats)


@pytest.mark.parametrize("text,expected", [
    ("1 month free! Sign by Oct 15", "2026-10-15"),
    ("$500 off. Offer expires 10/31/2026", "2026-10-31"),
    ("2 months free, valid through November 20", "2026-11-20"),
    ("Apply by 10/20 for 6 weeks free", "2026-10-20"),
])
def test_expiry(text, expected):
    assert p(text).expires == expected


@pytest.mark.parametrize("text,months", [
    ("1 month free on 13+ month leases", 13), ("1 month free on a 14 month lease", 14),
    ("Two months free on 12 month leases or longer", 12), ("1 month free, minimum 15-month lease", 15),
])
def test_min_lease(text, months):
    assert p(text).min_lease_months == months


def test_select_units_and_unparsed():
    t = p("1 month free on select units")
    assert t.select_units and t.parsed
    t = p("Special available", "See the property website for details.")
    assert not t.parsed


# ---------- effective rent ----------

def test_effective_two_months_on_15_month_lease():
    t = [p("Two Months Free", "Offer valid on 12+ month lease terms.")]
    e = effective_rent(1944, t, 15, "2026-11-17", "2026-10-04")
    assert e.rent == round(1944 * 13 / 15) == 1685 and e.savings == 259 and e.applied == ["Two Months Free"]


def test_effective_respects_min_lease():
    e = effective_rent(2000, [p("1 month free on 13+ month leases")], 12, None, "2026-10-04")
    assert e.rent == 2000 and e.applied == [] and "13+" in e.skipped[0]


def test_effective_move_in_deadline_per_unit():
    t = [p("1 month free when you move in by Nov 30")]
    early = effective_rent(1800, t, 12, "2026-11-15", "2026-10-04")
    late = effective_rent(1800, t, 12, "2026-12-10", "2026-10-04")
    assert early.rent == 1650 and late.rent == 1800 and "move-in deadline" in late.skipped[0]


def test_effective_move_in_deadline_already_passed():
    e = effective_rent(1800, [p("1 month free, move in by 2026-09-30")], 12, "2026-09-01", "2026-10-04")
    assert e.rent == 1800 and "has passed" in e.skipped[0]


def test_effective_expired_offer_and_mixed_specials():
    t = [p("1 month free, sign by Oct 1"), p("$600 off move-in")]
    e = effective_rent(1800, t, 12, None, "2026-10-04")
    assert e.applied == ["$600 off move-in"] and e.rent == 1750 and "ended" in e.skipped[0]


def test_effective_none_without_specials():
    assert effective_rent(1800, [], 12, None, "2026-10-04") is None
