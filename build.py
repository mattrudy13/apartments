"""Aggregate data/snapshots/*/*.json into the JSON the static site reads.

    site/data/summary.json   overview: latest numbers, deltas, history per complex
    site/data/<slug>.json    detail: latest floorplans + units (with effective rent and
                             listing history), price history per floorplan
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from scraper.run import MODULES
from scraper.specials import effective_rent, parse_special

ROOT = Path(__file__).resolve().parent
SNAPSHOTS = ROOT / "data" / "snapshots"
OUT = ROOT / "site" / "data"
DEFAULT_LEASE_MONTHS = 12  # used for effective rent when the site doesn't say


def bed_sort_key(label: str):
    """Studio, 1 BR, 2 BR, ... Other."""
    if label == "Studio":
        return 0.0
    try:
        return float(label.split()[0])
    except ValueError:
        return 99.0


def bed_label(beds) -> str:
    if beds is None:
        return "Other"
    return "Studio" if beds == 0 else f"{beds:g} BR"


def unit_key(u: dict) -> str:
    """Unit numbers repeat across buildings at some complexes, so key on both."""
    return f"{u.get('building') or ''}#{u['unit_number']}"


def normalize_specials(raw) -> List[dict]:
    """Old snapshots stored specials as plain titles."""
    return [s if isinstance(s, dict) else {"title": s, "description": ""} for s in raw or []]


# ---------- effective rent ----------

def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9$]+", " ", (title or "").lower()).strip()


def apply_specials(snap: dict, snap_date: str) -> None:
    """Annotate floorplans/units in place with parsed specials and effective rent."""
    ref = date.fromisoformat(snap_date)
    units_by_plan = defaultdict(list)
    for u in snap["units"]:
        units_by_plan[u["floorplan_code"]].append(u)

    # Site-wide banner specials apply to every floorplan, unless a floorplan already lists the
    # same offer (applying it twice would double the discount).
    for fp in snap["floorplans"]:
        fp["specials"] = normalize_specials(fp.get("specials"))
    fp_titles = {_norm_title(s["title"]) for fp in snap["floorplans"] for s in fp["specials"]}
    site_terms = []
    for s in normalize_specials(snap.get("property_specials")):
        t = parse_special(s["title"], s.get("description", ""), ref)
        t.site_wide = True
        if _norm_title(s["title"]) not in fp_titles:
            site_terms.append(t)
    snap["property_special_terms"] = [t.to_dict() for t in site_terms]

    for fp in snap["floorplans"]:
        fp_terms = [parse_special(s["title"], s.get("description", ""), ref) for s in fp["specials"]] + site_terms
        fp["special_terms"] = [t.to_dict() for t in fp_terms]

        def compute(price, lease, available, extra_specials=()):
            terms = fp_terms + [parse_special(s["title"], s.get("description", ""), ref) for s in extra_specials]
            eff = effective_rent(price, terms, lease or DEFAULT_LEASE_MONTHS, available, snap_date, beds=fp.get("beds"))
            return None if eff is None else {
                "rent": eff.rent, "savings": eff.savings, "applied": eff.applied, "skipped": eff.skipped,
                "uncertain": eff.uncertain, "lease_months": lease or DEFAULT_LEASE_MONTHS, "lease_assumed": not lease,
            }

        effs = []
        for u in units_by_plan.get(fp["code"], []):
            u["specials"] = normalize_specials(u.get("specials"))
            u["effective"] = compute(u["price"], u.get("lease_months") or fp.get("lease_months"),
                                     u.get("available_date"), u["specials"])
            if u["price"]:
                effs.append(u["effective"]["rent"] if u["effective"] else u["price"])
        if not effs and fp["units_available"] and fp["rent_min"]:
            fp_eff = compute(fp["rent_min"], fp.get("lease_months"), fp.get("earliest_available"))
            effs.append(fp_eff["rent"] if fp_eff else fp["rent_min"])
        fp["effective_min"] = min(effs) if effs and fp["units_available"] else None
        totals = [u.get("total_price") for u in units_by_plan.get(fp["code"], []) if u.get("total_price")]
        fp["total_min"] = min(totals) if totals else None


def unit_totals(snap: dict) -> List[Tuple[dict, int, int]]:
    """[(unit, total/mo, net total/mo)] for units whose total monthly cost is known: the site's
    total (rent + required fees), or the price itself when the site only shows totals.
    Net total = total minus the same specials savings applied to the rent."""
    total_basis = snap.get("price_basis") == "total"
    out = []
    for u in snap["units"]:
        total = u.get("total_price") or (u["price"] if total_basis else None)
        if total:
            savings = (u.get("effective") or {}).get("savings") or 0
            out.append((u, total, total - savings))
    return out


def metrics(snap: dict) -> dict:
    """Headline numbers for one snapshot (call apply_specials first)."""
    available = [fp for fp in snap["floorplans"] if fp["units_available"]]
    prices = [fp["rent_min"] for fp in available if fp["rent_min"]]
    prices += [u["price"] for u in snap["units"] if u["price"]]
    eff = [fp["effective_min"] for fp in available if fp.get("effective_min")]
    units = sum(fp["units_available"] for fp in snap["floorplans"])
    by_beds = defaultdict(lambda: {"units": 0, "min_price": None, "min_effective": None,
                                   "min_total": None, "min_total_net": None})

    def lower(b, key, val):
        if val and (b[key] is None or val < b[key]):
            b[key] = val

    for fp in available:
        b = by_beds[bed_label(fp["beds"])]
        b["units"] += fp["units_available"]
        lower(b, "min_price", fp["rent_min"])
        lower(b, "min_effective", fp.get("effective_min"))
    beds_of = {fp["code"]: bed_label(fp["beds"]) for fp in snap["floorplans"]}
    totals_known = unit_totals(snap)
    for u, total, net in totals_known:
        b = by_beds[beds_of.get(u["floorplan_code"], "Other")]
        lower(b, "min_total", total)
        lower(b, "min_total_net", net)
    return {
        "units": units,
        "min_price": min(prices) if prices else None,
        "min_effective": min(eff) if eff else None,
        "min_total": min(t for _, t, _ in totals_known) if totals_known else None,
        "min_total_net": min(n for _, _, n in totals_known) if totals_known else None,
        # Share of available units whose total monthly cost (with fees) is known.
        "total_known": round(len(totals_known) / len(snap["units"]), 2) if snap["units"] else 0,
        # False when units are listed but the site publishes no prices (e.g. "Rent: Call").
        "priced": bool(prices) or units == 0,
        "by_beds": dict(sorted(by_beds.items(), key=lambda kv: bed_sort_key(kv[0]))),
    }


# ---------- unit history ----------

def unit_histories(history: List[Tuple[str, dict]]) -> Tuple[dict, list]:
    """Per-unit listing history for units in the latest snapshot, plus units gone since the previous one.

    A listing "streak" starts the first pull a unit appears and resets if it drops off and
    comes back (re-listed after being leased).
    """
    streaks = {}  # key -> {"first_seen", "prices": [{date, price}]}
    prev_units = {}
    for d, snap in history:
        cur = {unit_key(u): u for u in snap["units"]}
        for k, u in cur.items():
            if k not in prev_units or k not in streaks:
                streaks[k] = {"first_seen": d, "prices": []}
            prices = streaks[k]["prices"]
            if u["price"] and (not prices or prices[-1]["price"] != u["price"]):
                prices.append({"date": d, "price": u["price"]})
        for k in list(streaks):
            if k not in cur:
                del streaks[k]
        prev_units, last_prev = cur, prev_units

    if not history:
        return {}, []
    latest_date = history[-1][0]
    multiple = len(history) > 1
    out = {}
    for k, st in streaks.items():
        prices = st["prices"]
        out[k] = {
            "first_seen": st["first_seen"],
            "days_listed": (date.fromisoformat(latest_date) - date.fromisoformat(st["first_seen"])).days,
            "is_new": multiple and st["first_seen"] == latest_date,
            "price_history": prices,
            "price_change": prices[-1]["price"] - prices[0]["price"] if len(prices) > 1 else 0,
            "price_changes": max(len(prices) - 1, 0),  # no prices at all ("Call") -> 0, not -1
        }
    gone = [
        {"unit_number": u["unit_number"], "building": u.get("building"), "floorplan_code": u["floorplan_code"],
         "last_price": u["price"], "last_seen": history[-2][0]}
        for k, u in last_prev.items() if k not in prev_units
    ] if multiple else []
    return out, gone


# ---------- data checks ----------

BIG_MOVE = 0.15  # a >15% price move in one pull is unusual enough to flag


def data_checks(window: List[Tuple[str, dict]], series: List[dict]) -> List[str]:
    """Reasons a complex's latest data looks off, comparing it only with itself (plans vs their
    own units, and this pull vs the previous one). Never compares across bedroom counts: a 2BR
    priced below a 1BR is normal."""
    if not window:
        return []
    date_, snap = window[-1]
    reasons = []
    units = snap["units"]

    # Plan counts vs unit rows (only meaningful when the site gives unit rows at all).
    if units:
        rows = defaultdict(int)
        for u in units:
            rows[u["floorplan_code"]] += 1
        off = [f"{fp['name']}: {fp['units_available']} available, {rows.get(fp['code'], 0)} listed"
               for fp in snap["floorplans"] if fp["units_available"] != rows.get(fp["code"], 0)]
        if off:
            reasons.append("Plan counts don't match unit lists (" + "; ".join(off[:3]) + (f"; +{len(off) - 3} more" if len(off) > 3 else "") + ")")
        missing = sum(1 for u in units if u["price"] is None)
        if 0 < missing < len(units):
            reasons.append(f"{missing} of {len(units)} units have no price")

    # This pull vs the previous one (within the same data source).
    cur = next((p for p in reversed(series) if p["date"] == date_), None)
    prev = next((p for p in reversed(series) if p["date"] < date_ and p["date"] >= window[0][0]), None)
    if cur and prev:
        if cur["min_price"] and prev["min_price"]:
            move = (cur["min_price"] - prev["min_price"]) / prev["min_price"]
            if abs(move) > BIG_MOVE:
                reasons.append(f"Lowest price moved {move:+.0%} since {prev['date']} (${prev['min_price']:,} → ${cur['min_price']:,})")
        if prev["units"] and not cur["units"]:
            reasons.append(f"No units available (had {prev['units']} on {prev['date']})")
        elif prev["units"] >= 5 and cur["units"] < prev["units"] * 0.4:
            reasons.append(f"Available units dropped from {prev['units']} to {cur['units']} since {prev['date']}")
    if len(window) > 1:
        before = {unit_key(u): u["price"] for u in window[-2][1]["units"] if u["price"]}
        jumps = []
        for u in units:
            old = before.get(unit_key(u))
            if old and u["price"] and abs(u["price"] - old) / old > BIG_MOVE:
                jumps.append(f"#{u['unit_number']} ${old:,} → ${u['price']:,}")
        if jumps:
            reasons.append("Unit price jumps over 15%: " + ", ".join(jumps[:3]) + (f", +{len(jumps) - 3} more" if len(jumps) > 3 else ""))
    return reasons


# ---------- build ----------

def delta(cur, prev):
    return None if cur is None or prev is None else cur - prev


def load_history(slug: str, snapshots: Path = SNAPSHOTS) -> list:
    """[(date, snapshot), ...] oldest first, with specials/effective rent applied."""
    out = []
    for path in sorted(snapshots.glob(f"*/{slug}.json")):
        snap = json.loads(path.read_text())
        apply_specials(snap, path.parent.name)
        out.append((path.parent.name, snap))
    return out


def build_complex(cfg: dict, history: list, st: dict) -> Tuple[dict, Optional[dict]]:
    slug = cfg["slug"]
    stale = not st.get("ok", True)
    error = st.get("error") if stale else None
    if not history:
        return {"slug": slug, "name": cfg["name"], "url": cfg.get("website") or cfg["url"],
                "stale": True, "error": error, "history": []}, None

    # Snapshots from before price_basis existed: use the scraper's declared basis.
    basis = getattr(MODULES.get(cfg.get("scraper")), "PRICE_BASIS", "base")
    for _, snap in history:
        snap["price_basis"] = snap.get("price_basis") or basis
    series = [{"date": d, **metrics(s)} for d, s in history]
    latest_date, latest = history[-1]
    cur, prev = series[-1], (series[-2] if len(series) > 1 else None)

    summary = {
        "slug": slug,
        "name": latest["name"],
        "url": latest["url"],
        "address": latest["property"].get("address"),
        "date": latest_date,
        "units": cur["units"],
        "min_price": cur["min_price"],
        "min_effective": cur["min_effective"],
        "min_total": cur["min_total"],
        "min_total_net": cur["min_total_net"],
        "total_known": cur["total_known"],
        "priced": cur["priced"],
        "price_basis": latest["price_basis"],
        "by_beds": cur["by_beds"],
        "units_delta": delta(cur["units"], prev and prev["units"]),
        "min_price_delta": delta(cur["min_price"], prev and prev["min_price"]),
        "min_effective_delta": delta(cur["min_effective"], prev and prev["min_effective"]),
        "prev_date": prev and prev["date"],
        "stale": stale,
        "error": error,
        "history": [{"date": p["date"], "units": p["units"], "min_price": p["min_price"],
                     "min_effective": p["min_effective"]} for p in series],
    }

    fp_history = defaultdict(list)
    for d, s in history:
        for fp in s["floorplans"]:
            fp_history[fp["code"]].append({
                "date": d,
                "rent_min": fp["rent_min"] if fp["units_available"] else None,
                "effective_min": fp.get("effective_min"),
                "units": fp["units_available"],
            })
    # After a data-source switch, unit IDs change (Attain: "4705-WSH #104" -> "4705 #104"), so
    # unit tracking restarts at `unit_history_since` instead of flagging every unit new/gone.
    since = str(cfg.get("unit_history_since") or "")
    unit_window = [(d, s) for d, s in history if d >= since] or history[-1:]
    uh, gone = unit_histories(unit_window)
    checks = data_checks(unit_window, series)
    summary["checks"] = checks
    for u in latest["units"]:
        u["history"] = uh.get(unit_key(u))
    detail = {
        **latest,
        "date": latest_date,
        "dates": [d for d, _ in history],
        "bed_history": [{"date": p["date"], "by_beds": p["by_beds"]} for p in series],
        "floorplan_history": fp_history,
        "gone_units": gone,
        "history_start": unit_window[0][0],
        "checks": checks,
        "stale": stale,
        "error": error,
    }
    return summary, detail


def build() -> None:
    complexes = yaml.safe_load((ROOT / "complexes.yaml").read_text())["complexes"]
    status_path = ROOT / "data" / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    OUT.mkdir(parents=True, exist_ok=True)

    summary = []
    for cfg in complexes:
        s, detail = build_complex(cfg, load_history(cfg["slug"]), status.get(cfg["slug"], {}))
        summary.append(s)
        if detail:
            (OUT / f"{cfg['slug']}.json").write_text(json.dumps(detail, separators=(",", ":")))

    (OUT / "summary.json").write_text(json.dumps({"complexes": summary}, indent=1))
    print(f"Built {len(summary)} complexes -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
