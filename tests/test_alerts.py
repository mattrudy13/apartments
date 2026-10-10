import base64
import json

import alerts


def unit(num, price, code="P1", building="A"):
    return {"unit_number": num, "building": building, "floorplan_code": code, "price": price, "sqft": 700,
            "available_date": "2026-11-01", "lease_months": None, "specials": []}


def snap(units, plans=None, specials=()):
    plans = plans or [{"code": "P1", "name": "Ash", "beds": 1}]
    return {
        "name": "Test", "url": "https://example.com", "property": {"address": None},
        "floorplans": [{**p, "sqft": 700, "rent_min": min((u["price"] for u in units if u["floorplan_code"] == p["code"]), default=None),
                        "units_available": sum(u["floorplan_code"] == p["code"] for u in units),
                        "earliest_available": None, "lease_months": None, "specials": list(specials)} for p in plans],
        "units": units,
    }


def write(tmp_path, slug, by_date):
    for d, s in by_date.items():
        (tmp_path / d).mkdir(exist_ok=True)
        (tmp_path / d / f"{slug}.json").write_text(json.dumps(s))


def config(shortlist=""):
    return {"shortlist": alerts.parse_shortlist(shortlist), "site_url": "https://example.com/"}


CRITERIA = {"beds": [1.0, 2.0], "max_monthly": 1900}


def digest(tmp_path, cfg, complexes=None, status=None, run_date=None):
    complexes = complexes or [{"slug": "t", "name": "Test"}]
    return alerts.build_digest(cfg, complexes, status or {}, run_date, snapshots=tmp_path, criteria=CRITERIA)


def test_baseline_is_about_a_week_back_not_the_mid_week_manual_run():
    dates = ["2026-10-05", "2026-10-06", "2026-10-12"]
    assert alerts.pick_baseline(dates, "2026-10-12") == "2026-10-06"
    assert alerts.pick_baseline(["2026-10-05", "2026-10-09", "2026-10-12"], "2026-10-12") == "2026-10-05"
    # Only recent pulls: fall back to the oldest earlier one; none at all: no baseline.
    assert alerts.pick_baseline(["2026-10-10", "2026-10-11", "2026-10-12"], "2026-10-12") == "2026-10-10"
    assert alerts.pick_baseline(["2026-10-12"], "2026-10-12") is None


def test_new_viable_units_price_drops_and_leased(tmp_path):
    write(tmp_path, "t", {
        "2026-10-05": snap([unit("101", 1600), unit("102", 1700), unit("103", 1800)]),
        "2026-10-12": snap([unit("101", 1550), unit("102", 1750), unit("104", 1650), unit("105", 2100)]),
    })
    d = digest(tmp_path, config())
    assert [r["unit"] for r in d["new_units"]] == ["#104 · Bldg A"]  # 105 is new but over the limit
    assert [(r["unit"], r["old_monthly"], r["monthly"]) for r in d["price_drops"]] == [("#101 · Bldg A", 1600, 1550)]
    c = d["complexes"][0]
    assert (c["leased"], c["priced_out"], c["viable_now"], c["viable_before"]) == (1, 0, 3, 3)
    assert alerts.subject(d) == "Apartments Oct 12: 1 new viable, 1 price drop"


def test_newly_viable_and_priced_out(tmp_path):
    write(tmp_path, "t", {
        "2026-10-05": snap([unit("101", 1950), unit("102", 1800), unit("103", 1850)]),
        "2026-10-12": snap([unit("101", 1850), unit("102", 1950), unit("103", 1850)]),
    })
    d = digest(tmp_path, config())
    assert [(r["unit"], r["old_monthly"]) for r in d["newly_viable"]] == [("#101 · Bldg A", 1950)]
    assert d["price_drops"] == [] and d["complexes"][0]["priced_out"] == 1
    assert "1 newly viable" in alerts.subject(d)


def test_new_special_makes_unit_viable_and_is_reported(tmp_path):
    special = {"title": "$100 Off Monthly Rent", "description": ""}
    write(tmp_path, "t", {
        "2026-10-05": snap([unit("101", 1950)]),
        "2026-10-12": snap([unit("101", 1950)], specials=[special]),
    })
    d = digest(tmp_path, config())
    assert [r["monthly"] for r in d["newly_viable"]] == [1850]
    assert d["specials"] == [("Test", ["$100 Off Monthly Rent"], [])]


def test_studios_and_3br_are_left_out(tmp_path):
    plans = [{"code": "P0", "name": "Loft", "beds": 0}, {"code": "P2", "name": "Oak", "beds": 2},
             {"code": "P3", "name": "Elm", "beds": 3}]
    write(tmp_path, "t", {
        "2026-10-05": snap([], plans),
        "2026-10-12": snap([unit("001", 1200, "P0"), unit("201", 1800, "P2"), unit("301", 1850, "P3")], plans),
    })
    d = digest(tmp_path, config())
    assert [r["plan"] for r in d["new_units"]] == ["Oak"]


def test_failed_and_skipped_complexes_are_flagged(tmp_path):
    write(tmp_path, "t", {"2026-10-05": snap([unit("101", 1600)]), "2026-10-12": snap([unit("101", 1600)])})
    write(tmp_path, "f", {"2026-10-05": snap([unit("101", 1600)])})
    write(tmp_path, "s", {"2026-10-05": snap([unit("101", 1600)])})
    complexes = [{"slug": "t", "name": "T"}, {"slug": "f", "name": "F"}, {"slug": "s", "name": "S"}]
    d = digest(tmp_path, config(), complexes, {"f": {"ok": False, "error": "HTTP 403"}})
    assert "F: scrape failed (HTTP 403)" in d["problems"] and "S: not scraped in this run" in d["problems"]
    assert d["new_units"] == [] and alerts.subject(d).endswith("1 scrape failed")


def share_link(entries):
    return "https://example.com/?shortlist=" + base64.urlsafe_b64encode(json.dumps(entries).encode()).decode().rstrip("=")


def test_shortlist_plan_opens_up_and_unit_goes(tmp_path):
    plans = [{"code": "P1", "name": "Ash", "beds": 1}, {"code": "P2", "name": "Oak", "beds": 2}]
    write(tmp_path, "t", {
        "2026-10-05": snap([unit("101", 1600, "P1")], plans),
        "2026-10-12": snap([unit("201", 1900, "P2")], plans),
    })
    link = share_link([{"id": "t|fp|P2", "kind": "plan", "slug": "t", "complex": "Test", "code": "P2", "label": "Oak"},
                       {"id": "t|u|A#101", "kind": "unit", "slug": "t", "complex": "Test", "unitKey": "A#101", "label": "#101"}])
    rows = digest(tmp_path, config(shortlist=link))["shortlist"]
    assert (rows[0]["status"], rows[0]["flag"]) == ("opened up: 1 unit from $1,900", "good")
    assert (rows[1]["status"], rows[1]["flag"]) == ("no longer listed", "bad")


def test_render_escapes_and_links(tmp_path):
    write(tmp_path, "t", {"2026-10-05": snap([]), "2026-10-12": snap([unit("<b>1", 1500)])})
    d = digest(tmp_path, config())
    html = alerts.render_html(d)
    assert "&lt;b&gt;1" in html and "<b>1" not in html
    assert 'href="https://example.com/complex.html?c=t"' in html
    assert "NEW VIABLE UNITS (1)" in alerts.render_text(d)


def test_load_env_reads_file_and_env_wins(tmp_path, monkeypatch):
    f = tmp_path / "alerts.env"
    f.write_text("# comment\nSMTP_USER=me@example.com\nSMTP_PASSWORD='abcd efgh'\n")
    monkeypatch.setenv("MAIL_TO", "other@example.com")
    env = alerts.load_env(f)
    assert env["SMTP_USER"] == "me@example.com" and env["SMTP_PASSWORD"] == "abcd efgh"
    assert env["MAIL_TO"] == "other@example.com"


def test_send_without_credentials_skips_quietly(monkeypatch, capsys):
    monkeypatch.setattr(alerts, "load_env", lambda path=None: {})
    assert alerts.main(["--send", "--failure", "git pull failed"]) == 0
    assert "not sending" in capsys.readouterr().out
