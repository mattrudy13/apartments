from datetime import date
from pathlib import Path

from scraper.banners import parse_banners

FIXTURES = Path(__file__).parent / "fixtures"
REF = date(2026, 10, 7)


def test_attain_banner_with_heading_and_fine_print():
    found = parse_banners((FIXTURES / "banner_attain.html").read_text(), ref=REF)
    assert [b["title"] for b in found] == [
        "MOVE IN BY OCTOBER 31 AND ENJOY $500 OFF 2-BEDROOM HOMES OR $1,000 OFF 3-BEDROOM HOMES!"]
    desc = found[0]["description"]
    assert desc.startswith("FALL INTO SAVINGS TODAY!") and "12+ month leases" in desc
    # Script text ("$999 off everything") is never read.
    assert all("999" not in b["title"] for b in found)


def test_north_hill_keeps_discount_and_skips_deposit_free():
    found = parse_banners((FIXTURES / "banner_northhill.html").read_text(), ref=REF)
    assert [b["title"] for b in found] == ["Enjoy 2 Weeks Base Rent Free When You Move In by May 31st!"]


def test_selector_narrows_and_no_promo_is_empty():
    html = (FIXTURES / "banner_attain.html").read_text()
    assert parse_banners(html, selector="nav", ref=REF) == []
    assert parse_banners("<html><body><h1>Welcome home</h1><p>Free Wi-Fi in the lounge</p></body></html>", ref=REF) == []
