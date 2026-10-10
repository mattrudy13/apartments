"""Weekly email digest: new units, price drops, units under your target prices, starred
floorplans/units, specials that started or ended, and scrape problems.

    python alerts.py --preview digest.html   # write the email to a file instead of sending
    python alerts.py --send                  # email it (SMTP settings from alerts.env)
    python alerts.py --send --failure "git pull failed"   # short failure notice only

Runs at the end of scripts/scrape_and_push.sh. What to watch is in alerts.yaml (committed);
SMTP credentials live outside the repo in ~/.config/apartments/alerts.env (see
alerts.env.example), or the file named by $APARTMENTS_ALERTS_ENV.
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

from build import SNAPSHOTS, bed_label, data_checks, load_history, metrics, normalize_specials, unit_key

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
    cfg["beds"] = [float(b) for b in cfg.get("beds") or []]
    cfg["targets"] = {float(k): int(v) for k, v in (cfg.get("targets") or {}).items()}
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
        "incl_fees": info["price_basis"] == "total",
    }


def special_titles(snap: dict) -> Dict[str, str]:
    """Normalized title -> display title, for floorplan and site-wide specials."""
    out = {}
    for s in normalize_specials(snap.get("property_specials")) + [
            s for fp in snap["floorplans"] for s in normalize_specials(fp.get("specials"))]:
        out[" ".join(s["title"].lower().split())] = s["title"]
    return out


def complex_changes(cfg: dict, history: list, run_date: str, st: dict) -> dict:
    """What changed at one complex between its baseline pull and run_date."""
    slug = cfg["slug"]
    dates = [d for d, _ in history]
    snaps = dict(history)
    out = {"slug": slug, "name": cfg["name"], "refreshed": run_date in snaps,
           "error": None if st.get("ok", True) else st.get("error"), "baseline": None,
           "new_units": [], "price_drops": [], "price_rises": 0, "gone": 0,
           "specials_started": [], "specials_ended": [], "checks": [], "units": [], "plans": {}}
    if not out["refreshed"]:
        return out
    latest = snaps[run_date]
    info = {"slug": slug, "name": latest.get("name") or cfg["name"],
            "price_basis": latest.get("price_basis") or "base"}
    out["name"] = info["name"]
    plans = {fp["code"]: fp for fp in latest["floorplans"]}
    out["units"] = [unit_row(u, plans.get(u["floorplan_code"], {}), info) for u in latest["units"]]
    out["unit_keys"] = {unit_key(u): row for u, row in zip(latest["units"], out["units"])}
    out["plans"] = plans
    cur = metrics(latest)
    out.update(units_now=cur["units"], min_price=cur["min_price"], min_effective=cur["min_effective"],
               incl_fees=info["price_basis"] == "total")

    # Data checks use the same window as the site, so the digest and the badge agree.
    since = str(cfg.get("unit_history_since") or "")
    window = [(d, s) for d, s in history if d >= since and d <= run_date]
    out["checks"] = data_checks(window, [{"date": d, **metrics(s)} for d, s in window])

    base_date = pick_baseline(dates, run_date)
    if not base_date:
        return out
    base = snaps[base_date]
    prev = metrics(base)
    out.update(baseline=base_date, units_before=prev["units"], min_price_before=prev["min_price"],
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
    out["base_unit_net"] = {k: net_rent(u) for k, u in before.items()}
    now_keys = set()
    for u, row in zip(latest["units"], out["units"]):
        k = unit_key(u)
        now_keys.add(k)
        old = before.get(k)
        if old is None:
            row["is_new"] = True
            out["new_units"].append(row)
        elif old.get("price") and u.get("price") and u["price"] != old["price"]:
            if u["price"] < old["price"]:
                row["old_price"] = old["price"]
                out["price_drops"].append(row)
            else:
                out["price_rises"] += 1
    out["gone"] = sum(1 for k in before if k not in now_keys)
    return out


# ---------- digest ----------

def shortlist_status(entries: List[dict], by_slug: Dict[str, dict]) -> List[dict]:
    """One line per starred floorplan/unit: what it looks like now vs the baseline."""
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
                 snapshots: Path = SNAPSHOTS, problems: List[str] = ()) -> dict:
    histories = {c["slug"]: load_history(c["slug"], snapshots) for c in complexes}
    run_date = run_date or max((h[-1][0] for h in histories.values() if h), default=date.today().isoformat())
    changes = [complex_changes(c, histories[c["slug"]], run_date, status.get(c["slug"], {})) for c in complexes]
    by_slug = {c["slug"]: c for c in changes}

    def beds_ok(row):
        return not cfg["beds"] or row["beds"] in cfg["beds"]

    # Only units that crossed under target since the baseline (new listings, or a price cut or
    # special that brought them under); the rest are counted, since they'd repeat every week.
    under, still_under = [], 0
    for c in changes:
        base_net = c.get("base_unit_net")
        for k, row in c.get("unit_keys", {}).items():
            target = cfg["targets"].get(row["beds"])
            if not (target and row["net"] and row["net"] <= target):
                continue
            was = base_net.get(k) if base_net is not None else None
            if base_net is None or was is None or was > target:
                under.append({**row, "target": target})
            else:
                still_under += 1
    under.sort(key=lambda r: r["net"])

    issues = list(problems)
    for c in changes:
        if not c["refreshed"]:
            issues.append(f"{c['name']}: scrape failed ({c['error']})" if c["error"]
                          else f"{c['name']}: not scraped in this run")
        issues += [f"{c['name']}: {r}" for r in c["checks"]]

    new_units = sorted((r for c in changes for r in c["new_units"] if beds_ok(r)),
                       key=lambda r: (r["complex"], r["net"] is None, r["net"] or 0))
    drops = sorted((r for c in changes for r in c["price_drops"] if beds_ok(r)),
                   key=lambda r: r["price"] - r["old_price"])
    return {
        "run_date": run_date, "site_url": cfg["site_url"], "problems": issues,
        "shortlist": shortlist_status(cfg["shortlist"], by_slug),
        "under_target": under, "still_under": still_under, "targets": cfg["targets"], "beds": cfg["beds"],
        "new_units": new_units, "price_drops": drops,
        "specials": [(c["name"], c["specials_started"], c["specials_ended"]) for c in changes
                     if c["specials_started"] or c["specials_ended"]],
        "complexes": changes,
    }


def subject(d: dict) -> str:
    when = date.fromisoformat(d["run_date"]).strftime("%b %-d")
    parts = [f"{len(d['new_units'])} new", f"{len(d['price_drops'])} price drop{'s' if len(d['price_drops']) != 1 else ''}"]
    if d["targets"]:
        parts.append(f"{len(d['under_target'])} newly under target")
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

    def price_cell(r):
        s = money(r["price"])
        if r["net"] != r["price"]:
            s += f'<br><span style="color:{MUTED};font-size:12px">net {money(r["net"])}</span>'
        return s

    # Three columns, so the tables still fit a phone screen without sideways scrolling.
    def unit_cells(r):
        sub = " · ".join(x for x in (f"{r['sqft']:,} sq ft" if r["sqft"] else "",
                                     f"avail. {short_date(r['available'])}" if r["available"] else "") if x)
        return [link(r["slug"], r["complex"]) + f'<br><span style="font-size:13px">{escape(r["unit"])}</span>',
                escape(f"{r['plan']} · {r['beds_label']}") + (f'<br><span style="color:{MUTED};font-size:12px">{sub}</span>' if sub else "")]

    parts = [f'<h1 style="font-size:20px;margin:0 0 4px">Apartments weekly digest</h1>'
             f'<p style="color:{MUTED};margin:0">Pull of {d["run_date"]} · <a href="{site}">open the site</a></p>']

    if d["problems"]:
        items = "".join(f'<li style="margin:2px 0">{escape(p)}</li>' for p in d["problems"])
        parts.append(_section("Needs attention", f'<ul style="margin:0;padding-left:20px;color:{BAD}">{items}</ul>',
                              "Check these on the complex's own site before trusting this week's numbers."))

    if d["shortlist"]:
        rows = [[link(r["slug"], r["complex"]), escape(r["label"]) + (" <span style='color:#666'>(plan)</span>" if r["kind"] == "plan" else ""),
                 color(r["flag"], escape(r["status"]))] for r in d["shortlist"]]
        parts.append(_section("Your shortlist", _table(["Complex", "Starred", "Now"], rows)))

    if d["targets"]:
        goals = ", ".join(f"{bed_label(b)} ≤ {money(v)}" for b, v in sorted(d["targets"].items()))
        rows = [unit_cells(r) + [price_cell(r) + ("<br><b style='font-size:12px'>NEW</b>" if r.get("is_new") else "")
                                 + (f"<br><span style='color:{GOOD};font-size:12px'>was {money(r['old_price'])}</span>" if r.get("old_price") else "")]
                for r in d["under_target"][:MAX_ROWS]]
        body = _table(["Unit", "Plan", "Price"], rows, right=(2,)) if rows else \
            f'<p style="margin:0;color:{MUTED}">Nothing new at or under target this week.</p>'
        still = f" {d['still_under']} other unit{'s' if d['still_under'] != 1 else ''} were already under target and still are." if d["still_under"] else ""
        parts.append(_section(f"Newly under your target ({len(d['under_target'])})", body + _more(len(d["under_target"]) - MAX_ROWS, site),
                              f"Targets: {goals}, compared with net rent after specials. Units that are new, or whose price or specials brought them under.{still}"))

    beds_note = f" Showing {', '.join(bed_label(b) for b in d['beds'])} only." if d["beds"] else ""
    rows = [unit_cells(r) + [price_cell(r)] for r in d["new_units"][:MAX_ROWS]]
    parts.append(_section(f"New units ({len(d['new_units'])})",
                          (_table(["Unit", "Plan", "Price"], rows, right=(2,)) if rows
                           else f'<p style="margin:0;color:{MUTED}">No new units.</p>') + _more(len(d["new_units"]) - MAX_ROWS, site),
                          "Listed now but not at the comparison pull." + beds_note))

    rows = [unit_cells(r) + [f"{money(r['old_price'])} → {money(r['price'])}<br><span style='color:{GOOD};font-size:12px'>{signed(r['price'] - r['old_price'])}</span>"]
            for r in d["price_drops"][:MAX_ROWS]]
    parts.append(_section(f"Price drops ({len(d['price_drops'])})",
                          (_table(["Unit", "Plan", "Listed price"], rows, right=(2,)) if rows
                           else f'<p style="margin:0;color:{MUTED}">No unit prices dropped.</p>') + _more(len(d["price_drops"]) - MAX_ROWS, site),
                          "Biggest drops first." + beds_note))

    if d["specials"]:
        items = ""
        for name, started, ended in d["specials"]:
            items += "".join(f"<li><b>{escape(name)}</b>: new: {escape(t)}</li>" for t in started)
            items += "".join(f"<li><b>{escape(name)}</b>: <span style='color:{MUTED}'>gone: {escape(t)}</span></li>" for t in ended)
        parts.append(_section("Specials", f'<ul style="margin:0;padding-left:20px">{items}</ul>'))

    rows = []
    for c in sorted(d["complexes"], key=lambda c: (c.get("min_effective") or c.get("min_price") or 10**9)):
        if not c["refreshed"]:
            rows.append([link(c["slug"], c["name"]), f"<span style='color:{BAD}'>{'failed' if c['error'] else 'not scraped'}</span>", "", "", ""])
            continue
        units_d = c["units_now"] - c["units_before"] if c.get("baseline") else 0
        price_d = (c["min_price"] - c["min_price_before"]) if c.get("baseline") and c["min_price"] and c["min_price_before"] else 0
        low = money(c["min_price"]) + (" incl. fees" if c["incl_fees"] and c["min_price"] else "")
        if price_d:
            low += f" <span style='color:{GOOD if price_d < 0 else BAD};font-size:12px'>{signed(price_d)}</span>"
        net = money(c["min_effective"]) if c["min_effective"] and c["min_effective"] != c["min_price"] else "—"
        units = f"{c['units_now']}" + (f" <span style='color:{MUTED};font-size:12px'>{signed(units_d, '')}</span>" if units_d else "")
        churn = f"+{len(c['new_units'])} / −{c['gone']}" if c.get("unit_baseline") else "first pull"
        rows.append([link(c["slug"], c["name"]), units, low, net, churn])
    parts.append(_section("All complexes", _table(["Complex", "Units", "Lowest", "Net", "New / gone"], rows, right=(1, 2, 3, 4)),
                          "Cheapest first. Changes compare with each complex's pull about a week earlier."))

    return (f'<!doctype html><html><body style="margin:0;padding:16px;background:#fff;color:#1a1a1a;{FONT}">'
            f'<div style="max-width:720px;margin:0 auto">{"".join(parts)}</div></body></html>')


def render_text(d: dict) -> str:
    def unit_line(r, extra=""):
        net = f" (net {money(r['net'])})" if r["net"] != r["price"] else ""
        when = f", available {r['available']}" if r["available"] else ""
        return f"- {r['complex']} {r['unit']} · {r['plan']} {r['beds_label']}: {money(r['price'])}{net}{extra}{when}"

    lines = [f"Apartments weekly digest, pull of {d['run_date']}", d["site_url"], ""]
    if d["problems"]:
        lines += ["NEEDS ATTENTION"] + [f"- {p}" for p in d["problems"]] + [""]
    if d["shortlist"]:
        lines += ["YOUR SHORTLIST"] + [f"- {r['complex']} {r['label']}: {r['status']}" for r in d["shortlist"]] + [""]
    if d["targets"]:
        lines += [f"NEWLY UNDER YOUR TARGET ({len(d['under_target'])}; {d['still_under']} others still under)"]
        lines += [unit_line(r, " NEW" if r.get("is_new") else (f", was {money(r['old_price'])}" if r.get("old_price") else ""))
                  for r in d["under_target"][:MAX_ROWS]] or ["- none"]
        lines += [""]
    lines += [f"NEW UNITS ({len(d['new_units'])})"] + ([unit_line(r) for r in d["new_units"][:MAX_ROWS]] or ["- none"]) + [""]
    lines += [f"PRICE DROPS ({len(d['price_drops'])})"]
    lines += [unit_line(r, f", was {money(r['old_price'])}") for r in d["price_drops"][:MAX_ROWS]] or ["- none"]
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
