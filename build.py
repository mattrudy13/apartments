"""Aggregate data/snapshots/*/*.json into the JSON the static site reads.

    site/data/summary.json   overview: latest numbers, deltas, history per complex
    site/data/<slug>.json    detail: latest floorplans + units (with effective rent and
                             listing history), price history per floorplan
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from scraper.specials import effective_rent, parse_special

ROOT = Path(__file__).resolve().parent
SNAPSHOTS = ROOT / "data" / "snapshots"
OUT = ROOT / "site" / "data"
DEFAULT_LEASE_MONTHS = 12  # used for effective rent when the site doesn't say


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

def apply_specials(snap: dict, snap_date: str) -> None:
    """Annotate floorplans/units in place with parsed specials and effective rent."""
    ref = date.fromisoformat(snap_date)
    units_by_plan = defaultdict(list)
    for u in snap["units"]:
        units_by_plan[u["floorplan_code"]].append(u)

    for fp in snap["floorplans"]:
        fp["specials"] = normalize_specials(fp.get("specials"))
        fp_terms = [parse_special(s["title"], s.get("description", ""), ref) for s in fp["specials"]]
        fp["special_terms"] = [t.to_dict() for t in fp_terms]

        def compute(price, lease, available, extra_specials=()):
            terms = fp_terms + [parse_special(s["title"], s.get("description", ""), ref) for s in extra_specials]
            eff = effective_rent(price, terms, lease or DEFAULT_LEASE_MONTHS, available, snap_date)
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


def metrics(snap: dict) -> dict:
    """Headline numbers for one snapshot (call apply_specials first)."""
    available = [fp for fp in snap["floorplans"] if fp["units_available"]]
    prices = [fp["rent_min"] for fp in available if fp["rent_min"]]
    prices += [u["price"] for u in snap["units"] if u["price"]]
    eff = [fp["effective_min"] for fp in available if fp.get("effective_min")]
    by_beds = defaultdict(lambda: {"units": 0, "min_price": None, "min_effective": None})
    for fp in available:
        b = by_beds[bed_label(fp["beds"])]
        b["units"] += fp["units_available"]
        for key, val in (("min_price", fp["rent_min"]), ("min_effective", fp.get("effective_min"))):
            if val and (b[key] is None or val < b[key]):
                b[key] = val
    return {
        "units": sum(fp["units_available"] for fp in snap["floorplans"]),
        "min_price": min(prices) if prices else None,
        "min_effective": min(eff) if eff else None,
        "by_beds": dict(sorted(by_beds.items())),
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
            "price_changes": len(prices) - 1,
        }
    gone = [
        {"unit_number": u["unit_number"], "building": u.get("building"), "floorplan_code": u["floorplan_code"],
         "last_price": u["price"], "last_seen": history[-2][0]}
        for k, u in last_prev.items() if k not in prev_units
    ] if multiple else []
    return out, gone


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
    uh, gone = unit_histories(history)
    for u in latest["units"]:
        u["history"] = uh.get(unit_key(u))
    detail = {
        **latest,
        "date": latest_date,
        "dates": [d for d, _ in history],
        "bed_history": [{"date": p["date"], "by_beds": p["by_beds"]} for p in series],
        "floorplan_history": fp_history,
        "gone_units": gone,
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
