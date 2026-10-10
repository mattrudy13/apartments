"""Weekly email digest of viable units (viable.yaml): new ones, ones that became viable,
price drops, starred floorplans/units, specials that started or ended, and scrape problems.

    python alerts.py --preview digest.html   # write the email to a file instead of sending
    python alerts.py --send                  # email it (SMTP settings from alerts.env)
    python alerts.py --send --failure "git pull failed"   # short failure notice only

Runs at the end of scripts/scrape_and_push.sh. Which units count is in viable.yaml (shared
with the site); the shortlist link is in alerts.yaml. SMTP credentials live outside the repo
in ~/.config/apartments/alerts.env (see alerts.env.example), or the file named by
$APARTMENTS_ALERTS_ENV.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import smtplib
import sys
from datetime import date, timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import yaml

from build import (SNAPSHOTS, bed_label, data_checks, load_history, load_viable_config, metrics,
                   normalize_specials, prepare_history, unit_key)

ROOT = Path(__file__).resolve().parent
DEFAULT_ENV = Path.home() / ".config" / "apartments" / "alerts.env"
DEFAULT_SITE = "https://mattrudy13.github.io/apartments/"
# A weekly digest compares with the pull about a week earlier, not just the previous one:
# manual `--only` runs mid-week would otherwise hide most of the week's changes.
BASELINE_DAYS = 6
MAX_ROWS = 25  # per section; the rest are counted and left to the site


# ---------- config ----------

def load_config(path: Path = ROOT / "alerts.yaml") -> dict:
    cfg = (yaml.safe_load(path.read_text()) if path.exists() else None) or {}
    cfg["shortlist"] = parse_shortlist(cfg.get("shortlist") or "")
    cfg["site_url"] = (cfg.get("site_url") or DEFAULT_SITE).rstrip("/") + "/"
    return cfg


def parse_shortlist(link: str) -> List[dict]:
    """Entries from the overview's "Copy share link" (?shortlist=<base64url JSON>)."""
    raw = parse_qs(urlparse(link.strip()).query).get("shortlist", [""])[0]
    if not raw:
        return []
    try:
        entries = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8"))
    except ValueError:
        raise SystemExit("alerts.yaml: shortlist isn't a valid share link (copy it again from the overview)")
    return [e for e in entries if isinstance(e, dict) and e.get("slug") and e.get("kind") in ("unit", "plan")]


def load_env(path: Optional[Path] = None) -> Dict[str, str]:
    """KEY=VALUE lines (blank lines and # comments ignored); real environment variables win."""
    path = path or Path(os.environ.get("APARTMENTS_ALERTS_ENV") or DEFAULT_ENV)
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    env.update({k: v for k, v in os.environ.items() if k.startswith(("SMTP_", "MAIL_"))})
    return env


# ---------- changes per complex ----------

def pick_baseline(dates: List[str], run_date: str) -> Optional[str]:
    """Newest pull at least BASELINE_DAYS before run_date, else the oldest earlier one."""
    earlier = [d for d in dates if d < run_date]
    if not earlier:
        return None
    cutoff = (date.fromisoformat(run_date) - timedelta(days=BASELINE_DAYS)).isoformat()
    old_enough = [d for d in earlier if d <= cutoff]
    return old_enough[-1] if old_enough else earlier[0]


def net_rent(u: dict) -> Optional[int]:
    """Effective rent when specials lower it, else the listed price."""
    eff = u.get("effective") or {}
    return eff["rent"] if eff.get("applied") else u.get("price")


def unit_row(u: dict, plan: dict, info: dict) -> dict:
    return {
        "slug": info["slug"], "complex": info["name"],
        "unit": f"#{u['unit_number']}" + (f" · Bldg {u['building']}" if u.get("building") else ""),
        "plan": plan.get("name") or u["floorplan_code"], "beds": plan.get("beds"),
        "beds_label": bed_label(plan.get("beds")), "sqft": u.get("sqft") or plan.get("sqft"),
        "price": u.get("price"), "net": net_rent(u), "available": u.get("available_date"),
        "monthly": u.get("monthly"), "fees_known": u.get("fees_known"), "viable": u.get("viable"),
    }


def special_titles(snap: dict) -> Dict[str, str]:
    """Normalized title -> display title, for floorplan and site-wide specials."""
    out = {}
    for s in normalize_specials(snap.get("property_specials")) + [
            s for fp in snap["floorplans"] for s in normalize_specials(fp.get("specials"))]:
        out[" ".join(s["title"].lower().split())] = s["title"]
    return out


def complex_changes(cfg: dict, history: list, run_date: str, st: dict) -> dict:
    """What changed at one complex between its baseline pull and run_date, for viable units
    (call prepare_history first so units carry monthly/viable)."""
    slug = cfg["slug"]
    dates = [d for d, _ in history]
    snaps = dict(history)
    out = {"slug": slug, "name": cfg["name"], "refreshed": run_date in snaps,
           "error": None if st.get("ok", True) else st.get("error"), "baseline": None,
           "new_units": [], "newly_viable": [], "price_drops": [], "leased": 0, "priced_out": 0,
           "specials_started": [], "specials_ended": [], "checks": [], "units": [], "plans": {}}
    if not out["refreshed"]:
        return out
    latest = snaps[run_date]
    info = {"slug": slug, "name": latest.get("name") or cfg["name"]}
    out["name"] = info["name"]
    plans = {fp["code"]: fp for fp in latest["floorplans"]}
    out["units"] = [unit_row(u, plans.get(u["floorplan_code"], {}), info) for u in latest["units"]]
    out["unit_keys"] = {unit_key(u): row for u, row in zip(latest["units"], out["units"])}
    out["plans"] = plans
    cur = metrics(latest)
    out.update(viable_now=cur["viable_units"], viable_min=cur["viable_min"])

    # Data checks use the same window as the site, so the digest and the badge agree.
    since = str(cfg.get("unit_history_since") or "")
    window = [(d, s) for d, s in history if d >= since and d <= run_date]
    out["checks"] = data_checks(window, [{"date": d, **metrics(s)} for d, s in window])

    base_date = pick_baseline(dates, run_date)
    if not base_date:
        return out
    base = snaps[base_date]
    prev = metrics(base)
    out.update(baseline=base_date, viable_before=prev["viable_units"], viable_min_before=prev["viable_min"],
               base_plans={fp["code"]: fp for fp in base["floorplans"]})

    now_t, before_t = special_titles(latest), special_titles(base)
    out["specials_started"] = [t for k, t in now_t.items() if k not in before_t]
    out["specials_ended"] = [t for k, t in before_t.items() if k not in now_t]

    # Unit IDs change when a site switches data source, so units compare only from `since`.
    unit_base_date = pick_baseline([d for d in dates if d >= since], run_date)
    if not unit_base_date:
        return out
    out["unit_baseline"] = unit_base_date
    before = {unit_key(u): u for u in snaps[unit_base_date]["units"]}
    out["base_unit_prices"] = {k: u.get("price") for k, u in before.items()}
    for k, row in out["unit_keys"].items():
        old = before.get(k)
        if not row["viable"]:
            continue
        if old is None:
            row["is_new"] = True
            out["new_units"].append(row)
        elif not old.get("viable"):
            row["old_monthly"] = old.get("monthly")
            out["newly_viable"].append(row)
        # Monthly, not listed price, so a new special or a fee change counts too.
        elif old.get("monthly") and row["monthly"] < old["monthly"]:
            row["old_monthly"] = old["monthly"]
            out["price_drops"].append(row)
    for k, old in before.items():
        if old.get("viable"):
            now = out["unit_keys"].get(k)
            if now is None:
                out["leased"] += 1
            elif not now["viable"]:
                out["priced_out"] += 1
    return out


# ---------- digest ----------

def shortlist_status(entries: List[dict], by_slug: Dict[str, dict]) -> List[dict]:
    """One line per starred floorplan/unit (viable or not): what it looks like now vs the baseline."""
    rows = []
    for e in entries:
        c = by_slug.get(e["slug"])
        row = {"complex": e.get("complex") or e["slug"], "slug": e["slug"], "label": e.get("label") or e.get("code"),
               "kind": e["kind"], "status": "", "flag": None}
        if not c or not c["refreshed"]:
            row["status"] = "no new data this week"
        elif e["kind"] == "plan":
            fp = c["plans"].get(e.get("code"))
            old = (c.get("base_plans") or {}).get(e.get("code"))
            if not fp:
                row["status"], row["flag"] = "floorplan no longer listed", "bad"
            elif not fp["units_available"]:
                row["status"] = "no units available"
                if old and old["units_available"]:
                    row["status"], row["flag"] = f"no units available (had {old['units_available']})", "bad"
            else:
                n = fp["units_available"]
                price = fp.get("effective_min") or fp.get("rent_min")
                row["status"] = f"{n} unit{'s' if n != 1 else ''} from {money(price)}"
                if old is not None and not old["units_available"]:
                    row["status"], row["flag"] = "opened up: " + row["status"], "good"
                elif old and old.get("rent_min") and fp.get("rent_min") and fp["rent_min"] != old["rent_min"]:
                    row["status"] += f" (was {money(old['rent_min'])})"
                    row["flag"] = "good" if fp["rent_min"] < old["rent_min"] else "bad"
        else:
            u = c.get("unit_keys", {}).get(e.get("unitKey"))
            if not u:
                row["status"], row["flag"] = "no longer listed", "bad"
            else:
                row["status"] = money(u["price"]) + (f" (net {money(u['net'])})" if u["net"] != u["price"] else "")
                old = (c.get("base_unit_prices") or {}).get(e.get("unitKey"))
                if old and u["price"] and u["price"] != old:
                    row["status"] += f", was {money(old)}"
                    row["flag"] = "good" if u["price"] < old else "bad"
        rows.append(row)
    return rows


def build_digest(cfg: dict, complexes: List[dict], status: dict, run_date: Optional[str] = None,
                 snapshots: Path = SNAPSHOTS, problems: List[str] = (), criteria: Optional[dict] = None) -> dict:
    criteria = criteria if criteria is not None else load_viable_config()
    histories = {c["slug"]: prepare_history(c, load_history(c["slug"], snapshots), criteria) for c in complexes}
    run_date = run_date or max((h[-1][0] for h in histories.values() if h), default=date.today().isoformat())
    changes = [complex_changes(c, histories[c["slug"]], run_date, status.get(c["slug"], {})) for c in complexes]
    by_slug = {c["slug"]: c for c in changes}

    issues = list(problems)
    for c in changes:
        if not c["refreshed"]:
            issues.append(f"{c['name']}: scrape failed ({c['error']})" if c["error"]
                          else f"{c['name']}: not scraped in this run")
        issues += [f"{c['name']}: {r}" for r in c["checks"]]

    by_monthly = lambda r: r["monthly"]
    return {
        "run_date": run_date, "site_url": cfg["site_url"], "problems": issues, "criteria": criteria,
        "shortlist": shortlist_status(cfg["shortlist"], by_slug),
        "new_units": sorted((r for c in changes for r in c["new_units"]), key=by_monthly),
        "newly_viable": sorted((r for c in changes for r in c["newly_viable"]), key=by_monthly),
        "price_drops": sorted((r for c in changes for r in c["price_drops"]), key=lambda r: r["monthly"] - r["old_monthly"]),
        "viable_now": sum(c.get("viable_now") or 0 for c in changes),
        "specials": [(c["name"], c["specials_started"], c["specials_ended"]) for c in changes
                     if c["specials_started"] or c["specials_ended"]],
        "complexes": changes,
    }


def criteria_text(c: dict) -> str:
    beds = [bed_label(b) for b in c.get("beds") or []]
    text = (", ".join(beds[:-1]) + " or " + beds[-1]) if len(beds) > 1 else (beds[0] if beds else "Any size")
    return text + (f" under {money(c['max_monthly'])}/mo" if c.get("max_monthly") else "")


def subject(d: dict) -> str:
    when = date.fromisoformat(d["run_date"]).strftime("%b %-d")
    drops = len(d["price_drops"])
    parts = [f"{len(d['new_units'])} new viable"]
    if d["newly_viable"]:
        parts.append(f"{len(d['newly_viable'])} newly viable")
    parts.append(f"{drops} price drop{'s' if drops != 1 else ''}")
    failed = sum(1 for c in d["complexes"] if not c["refreshed"] and c["error"])
    if failed:
        parts.append(f"{failed} scrape{'s' if failed != 1 else ''} failed")
    return f"Apartments {when}: " + ", ".join(parts)


# ---------- rendering ----------

def money(v) -> str:
    return "Call" if v is None else f"${v:,}"


def short_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%b %-d")


def signed(v, unit="$") -> str:
    if not v:
        return ""
    return f"{'+' if v > 0 else '−'}{unit}{abs(v):,}" if unit else f"{'+' if v > 0 else '−'}{abs(v):,}"


# Inline styles only: many mail clients drop <style> blocks. Colors match the site
# (price down = green, up = red) and stay readable when a client inverts for dark mode.
FONT = "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
TH = "text-align:left;padding:6px 10px 6px 0;border-bottom:1px solid #ccc;font-size:12px;color:#555;font-weight:600;"
TD = "padding:6px 10px 6px 0;border-bottom:1px solid #eee;font-size:14px;vertical-align:top;"
GOOD, BAD, MUTED = "#1a7f37", "#c62828", "#666"


def _table(headers: List[str], rows: List[List[str]], right=()) -> str:
    head = "".join(f'<th style="{TH}{"text-align:right;" if i in right else ""}">{h}</th>' for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td style="{TD}{"text-align:right;white-space:nowrap;" if i in right else ""}">{c}</td>'
                                    for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;margin:4px 0 8px">{head and "<tr>" + head + "</tr>"}{body}</table>'


def _more(n: int, url: str) -> str:
    return f'<p style="font-size:13px;color:{MUTED};margin:0 0 8px">+{n} more on <a href="{url}">the site</a></p>' if n > 0 else ""


def _section(title: str, body: str, note: str = "") -> str:
    note_html = f'<p style="font-size:13px;color:{MUTED};margin:0 0 6px">{note}</p>' if note else ""
    return f'<h2 style="font-size:17px;margin:24px 0 6px">{title}</h2>{note_html}{body}'


def render_html(d: dict) -> str:
    site = d["site_url"]
    link = lambda slug, text: f'<a href="{site}complex.html?c={slug}" style="color:inherit">{escape(text)}</a>'
    color = lambda flag, text: f'<span style="color:{GOOD if flag == "good" else BAD}">{text}</span>' if flag else text
    small = lambda text, c=MUTED: f'<br><span style="color:{c};font-size:12px">{text}</span>'

    def monthly_cell(r, was=False):
        s = f"{money(r['old_monthly'])} → {money(r['monthly'])}" if was and r.get("old_monthly") else money(r["monthly"])
        if was and r.get("old_monthly"):
            s += small(signed(r["monthly"] - r["old_monthly"]), GOOD)
        return s + ("" if r["fees_known"] else small("fees not listed"))

    # Three columns, so the tables still fit a phone screen without sideways scrolling.
    def unit_cells(r):
        sub = " · ".join(x for x in (f"{r['sqft']:,} sq ft" if r["sqft"] else "",
                                     f"avail. {short_date(r['available'])}" if r["available"] else "") if x)
        return [link(r["slug"], r["complex"]) + f'<br><span style="font-size:13px">{escape(r["unit"])}</span>',
                escape(f"{r['plan']} · {r['beds_label']}") + (small(sub) if sub else "")]

    def unit_section(title, rows_in, empty, note, was=False):
        rows = [unit_cells(r) + [monthly_cell(r, was)] for r in rows_in[:MAX_ROWS]]
        body = (_table(["Unit", "Plan", "Per month"], rows, right=(2,)) if rows
                else f'<p style="margin:0;color:{MUTED}">{empty}</p>') + _more(len(rows_in) - MAX_ROWS, site)
        return _section(f"{title} ({len(rows_in)})", body, note)

    parts = [f'<h1 style="font-size:20px;margin:0 0 4px">Apartments weekly digest</h1>'
             f'<p style="color:{MUTED};margin:0">Pull of {d["run_date"]} · {d["viable_now"]} viable units '
             f'({escape(criteria_text(d["criteria"]))}) · <a href="{site}">open the site</a></p>']

    if d["problems"]:
        items = "".join(f'<li style="margin:2px 0">{escape(p)}</li>' for p in d["problems"])
        parts.append(_section("Needs attention", f'<ul style="margin:0;padding-left:20px;color:{BAD}">{items}</ul>',
                              "Check these on the complex's own site before trusting this week's numbers."))

    if d["shortlist"]:
        rows = [[link(r["slug"], r["complex"]), escape(r["label"]) + (" <span style='color:#666'>(plan)</span>" if r["kind"] == "plan" else ""),
                 color(r["flag"], escape(r["status"]))] for r in d["shortlist"]]
        parts.append(_section("Your shortlist", _table(["Complex", "Starred", "Now"], rows)))

    parts.append(unit_section("New viable units", d["new_units"], "No new viable units.",
                              "Listed now but not at the comparison pull. Cheapest first."))
    if d["newly_viable"]:
        parts.append(unit_section("Newly viable", d["newly_viable"], "",
                                  "Already listed, but a price cut or special brought them under the limit.", was=True))
    parts.append(unit_section("Price drops", d["price_drops"], "No viable units got cheaper.",
                              "Viable units whose monthly cost (after specials, with listed fees) fell. Biggest drops first.", was=True))

    if d["specials"]:
        items = ""
        for name, started, ended in d["specials"]:
            items += "".join(f"<li><b>{escape(name)}</b>: new: {escape(t)}</li>" for t in started)
            items += "".join(f"<li><b>{escape(name)}</b>: <span style='color:{MUTED}'>gone: {escape(t)}</span></li>" for t in ended)
        parts.append(_section("Specials", f'<ul style="margin:0;padding-left:20px">{items}</ul>'))

    rows = []
    for c in sorted(d["complexes"], key=lambda c: (c.get("viable_min") or 10**9, c["name"])):
        if not c["refreshed"]:
            rows.append([link(c["slug"], c["name"]), f"<span style='color:{BAD}'>{'failed' if c['error'] else 'not scraped'}</span>", "", ""])
            continue
        n_d = c["viable_now"] - c["viable_before"] if c.get("baseline") else 0
        low_d = (c["viable_min"] - c["viable_min_before"]) if c.get("baseline") and c["viable_min"] and c["viable_min_before"] else 0
        count = f"{c['viable_now']}" + (f" <span style='color:{MUTED};font-size:12px'>{signed(n_d, '')}</span>" if n_d else "")
        low = money(c["viable_min"]) if c["viable_min"] else "—"
        if low_d:
            low += f" <span style='color:{GOOD if low_d < 0 else BAD};font-size:12px'>{signed(low_d)}</span>"
        left = (f"{c['leased']} / {c['priced_out']}" if c["leased"] or c["priced_out"] else "—") if c.get("unit_baseline") else "first pull"
        rows.append([link(c["slug"], c["name"]), count, low, left])
    parts.append(_section("All complexes", _table(["Complex", "Viable", "Cheapest", "Left / over"], rows, right=(1, 2, 3)),
                          "Cheapest viable first. “Left / over”: viable units that are no longer listed (likely leased) / now cost too much. "
                          "Changes compare with each complex's pull about a week earlier."))

    return (f'<!doctype html><html><body style="margin:0;padding:16px;background:#fff;color:#1a1a1a;{FONT}">'
            f'<div style="max-width:720px;margin:0 auto">{"".join(parts)}</div></body></html>')


def render_text(d: dict) -> str:
    def unit_line(r, was=False):
        cost = f"{money(r['old_monthly'])} -> {money(r['monthly'])}" if was and r.get("old_monthly") else money(r["monthly"])
        fees = "" if r["fees_known"] else " (fees not listed)"
        when = f", available {r['available']}" if r["available"] else ""
        return f"- {r['complex']} {r['unit']} · {r['plan']} {r['beds_label']}: {cost}/mo{fees}{when}"

    lines = [f"Apartments weekly digest, pull of {d['run_date']}",
             f"{d['viable_now']} viable units ({criteria_text(d['criteria'])})", d["site_url"], ""]
    if d["problems"]:
        lines += ["NEEDS ATTENTION"] + [f"- {p}" for p in d["problems"]] + [""]
    if d["shortlist"]:
        lines += ["YOUR SHORTLIST"] + [f"- {r['complex']} {r['label']}: {r['status']}" for r in d["shortlist"]] + [""]
    lines += [f"NEW VIABLE UNITS ({len(d['new_units'])})"] + ([unit_line(r) for r in d["new_units"][:MAX_ROWS]] or ["- none"]) + [""]
    if d["newly_viable"]:
        lines += [f"NEWLY VIABLE ({len(d['newly_viable'])})"] + [unit_line(r, True) for r in d["newly_viable"][:MAX_ROWS]] + [""]
    lines += [f"PRICE DROPS ({len(d['price_drops'])})"]
    lines += [unit_line(r, True) for r in d["price_drops"][:MAX_ROWS]] or ["- none"]
    if d["specials"]:
        lines += ["", "SPECIALS"]
    for name, started, ended in d["specials"]:
        lines += [f"- {name}: new: {t}" for t in started] + [f"- {name}: gone: {t}" for t in ended]
    return "\n".join(lines) + "\n"


# ---------- sending ----------

def send(subject_line: str, text: str, html: Optional[str], env: Dict[str, str]) -> None:
    user, password = env.get("SMTP_USER"), env.get("SMTP_PASSWORD")
    msg = EmailMessage()
    msg["Subject"] = subject_line
    msg["From"] = env.get("MAIL_FROM") or user
    msg["To"] = env.get("MAIL_TO") or user
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    host, port = env.get("SMTP_HOST") or "smtp.gmail.com", int(env.get("SMTP_PORT") or 587)
    with (smtplib.SMTP_SSL(host, port, timeout=30) if port == 465 else smtplib.SMTP(host, port, timeout=30)) as s:
        if port != 465:
            s.starttls()
        s.login(user, password)
        s.send_message(msg)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--send", action="store_true", help="email the digest")
    p.add_argument("--preview", metavar="FILE", help="write the HTML email to FILE")
    p.add_argument("--date", help="pull to report on (default: the newest snapshot)")
    p.add_argument("--problem", action="append", default=[], help="extra line for 'Needs attention'")
    p.add_argument("--failure", metavar="MSG", help="send only a short failure notice")
    args = p.parse_args(argv)

    if args.failure:
        subj, text, html = "Apartments: weekly job failed", f"{args.failure}\n\nLog: ~/Library/Logs/apartments-scraper.log\n", None
    else:
        complexes = yaml.safe_load((ROOT / "complexes.yaml").read_text())["complexes"]
        status_path = ROOT / "data" / "status.json"
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
        d = build_digest(load_config(), complexes, status, args.date, problems=args.problem)
        subj, text, html = subject(d), render_text(d), render_html(d)
    if args.preview:
        Path(args.preview).write_text(html or text)
        print(f"Wrote {args.preview}: {subj}")
    if not args.send:
        if not args.preview:
            print(subj + "\n\n" + text)
        return 0

    env = load_env()
    if not (env.get("SMTP_USER") and env.get("SMTP_PASSWORD")):
        # Not set up yet (or on another machine): skip quietly rather than fail the weekly job.
        print("alerts: no SMTP_USER/SMTP_PASSWORD (see alerts.env.example); not sending")
        return 0
    send(subj, text, html, env)
    print(f"alerts: sent \"{subj}\" to {env.get('MAIL_TO') or env['SMTP_USER']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
