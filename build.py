"""Aggregate data/snapshots/*/*.json into the JSON the static site reads.

    site/data/summary.json   overview: latest numbers, deltas, history per complex
    site/data/<slug>.json    detail: latest floorplans + units, price history per floorplan
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
SNAPSHOTS = ROOT / "data" / "snapshots"
OUT = ROOT / "site" / "data"


def bed_label(beds) -> str:
    if beds is None:
        return "Other"
    return "Studio" if beds == 0 else f"{beds:g} BR"


def metrics(snap: dict) -> dict:
    """Headline numbers for one snapshot."""
    available = [fp for fp in snap["floorplans"] if fp["units_available"]]
    prices = [fp["rent_min"] for fp in available if fp["rent_min"]]
    prices += [u["price"] for u in snap["units"] if u["price"]]
    by_beds = defaultdict(lambda: {"units": 0, "min_price": None})
    for fp in available:
        b = by_beds[bed_label(fp["beds"])]
        b["units"] += fp["units_available"]
        if fp["rent_min"] and (b["min_price"] is None or fp["rent_min"] < b["min_price"]):
            b["min_price"] = fp["rent_min"]
    return {
        "units": sum(fp["units_available"] for fp in snap["floorplans"]),
        "min_price": min(prices) if prices else None,
        "by_beds": dict(sorted(by_beds.items())),
    }


def delta(cur, prev):
    return None if cur is None or prev is None else cur - prev


def load_history(slug: str) -> list:
    """[(date, snapshot), ...] oldest first."""
    return [
        (path.parent.name, json.loads(path.read_text()))
        for path in sorted(SNAPSHOTS.glob(f"*/{slug}.json"))
    ]


def build() -> None:
    complexes = yaml.safe_load((ROOT / "complexes.yaml").read_text())["complexes"]
    status_path = ROOT / "data" / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    OUT.mkdir(parents=True, exist_ok=True)

    summary = []
    for cfg in complexes:
        slug = cfg["slug"]
        history = load_history(slug)
        st = status.get(slug, {})
        if not history:
            summary.append({"slug": slug, "name": cfg["name"], "url": cfg.get("website") or cfg["url"],
                            "stale": True, "error": st.get("error"), "history": []})
            continue

        series = [{"date": d, **metrics(s)} for d, s in history]
        latest_date, latest = history[-1]
        cur, prev = series[-1], (series[-2] if len(series) > 1 else None)

        summary.append({
            "slug": slug,
            "name": latest["name"],
            "url": latest["url"],
            "address": latest["property"].get("address"),
            "date": latest_date,
            "units": cur["units"],
            "min_price": cur["min_price"],
            "by_beds": cur["by_beds"],
            "units_delta": delta(cur["units"], prev and prev["units"]),
            "min_price_delta": delta(cur["min_price"], prev and prev["min_price"]),
            "prev_date": prev and prev["date"],
            "stale": not st.get("ok", True),
            "error": None if st.get("ok", True) else st.get("error"),
            "history": [{"date": p["date"], "units": p["units"], "min_price": p["min_price"]} for p in series],
        })

        # Per-floorplan history: rent_min/units at every snapshot (null when nothing was available).
        fp_history = defaultdict(list)
        for d, s in history:
            for fp in s["floorplans"]:
                fp_history[fp["code"]].append({
                    "date": d,
                    "rent_min": fp["rent_min"] if fp["units_available"] else None,
                    "units": fp["units_available"],
                })
        detail = {
            **latest,
            "date": latest_date,
            "dates": [d for d, _ in history],
            "bed_history": [{"date": p["date"], "by_beds": p["by_beds"]} for p in series],
            "floorplan_history": fp_history,
            "stale": not st.get("ok", True),
            "error": None if st.get("ok", True) else st.get("error"),
        }
        (OUT / f"{slug}.json").write_text(json.dumps(detail, separators=(",", ":")))

    (OUT / "summary.json").write_text(json.dumps({"complexes": summary}, indent=1))
    print(f"Built {len(summary)} complexes -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
