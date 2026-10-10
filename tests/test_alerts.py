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


def config(targets=None, beds=None, shortlist=""):
    return {"targets": targets or {}, "beds": beds or [], "shortlist": alerts.parse_shortlist(shortlist),
            "site_url": "https://example.com/"}


def digest(tmp_path, cfg, complexes=None, status=None, run_date=None):
    complexes = complexes or [{"slug": "t", "name": "Test"}]
    return alerts.build_digest(cfg, complexes, status or {}, run_date, snapshots=tmp_path)


def test_baseline_is_about_a_week_back_not_the_mid_week_manual_run():
    dates = ["2026-10-05", "2026-10-06", "2026-10-12"]
    assert alerts.pick_baseline(dates, "2026-10-12") == "2026-10-06"
    assert alerts.pick_baseline(["2026-10-05", "2026-10-09", "2026-10-12"], "2026-10-12") == "2026-10-05"
    # Only recent pulls: fall back to the oldest earlier one; none at all: no baseline.
    assert alerts.pick_baseline(["2026-10-10", "2026-10-11", "2026-10-12"], "2026-10-12") == "2026-10-10"
    assert alerts.pick_baseline(["2026-10-12"], "2026-10-12") is None


def test_new_units_price_drops_and_gone(tmp_path):
    write(tmp_path, "t", {
        "2026-10-05": snap([unit("101", 1600), unit("102", 1700), unit("103", 1800)]),
        "2026-10-12": snap([unit("101", 1550), unit("102", 1750), unit("104", 1650)]),
    })
    d = digest(tmp_path, config())
    assert [r["unit"] for r in d["new_units"]] == ["#104 · Bldg A"]
    assert [(r["unit"], r["old_price"], r["price"]) for r in d["price_drops"]] == [("#101 · Bldg A", 1600, 1550)]
    c = d["complexes"][0]
    assert c["gone"] == 1 and c["price_rises"] == 1
    assert alerts.subject(d) == "Apartments Oct 12: 1 new, 1 price drop"


def test_target_reports_only_units_that_crossed_under(tmp_path):
    write(tmp_path, "t", {
        "2026-10-05": snap([unit("101", 1600), unit("102", 1450), unit("103", 1700)]),
        "2026-10-12": snap([unit("101", 1490), unit("102", 1450), unit("103", 1700), unit("104", 1400)]),
    })
    d = digest(tmp_path, config(targets={1.0: 1500}))
    assert sorted(r["unit"] for r in d["under_target"]) == ["#101 · Bldg A", "#104 · Bldg A"]
    assert d["still_under"] == 1  # 102 was already under target


def test_new_special_counts_toward_target_and_is_reported(tmp_path):
    special = {"title": "$200 Off Monthly Rent", "description": ""}
    write(tmp_path, "t", {
        "2026-10-05": snap([unit("101", 1600)]),
        "2026-10-12": snap([unit("101", 1600)], specials=[special]),
    })
    d = digest(tmp_path, config(targets={1.0: 1500}))
    assert [r["net"] for r in d["under_target"]] == [1400]
    assert d["specials"] == [("Test", ["$200 Off Monthly Rent"], [])]


def test_beds_filter_limits_new_units(tmp_path):
    plans = [{"code": "P1", "name": "Ash", "beds": 1}, {"code": "P2", "name": "Oak", "beds": 2}]
    write(tmp_path, "t", {
        "2026-10-05": snap([], plans),
        "2026-10-12": snap([unit("101", 1500, "P1"), unit("201", 1900, "P2")], plans),
    })
    d = digest(tmp_path, config(beds=[2.0]))
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
    assert "NEW UNITS (1)" in alerts.render_text(d)


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
