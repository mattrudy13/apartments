"""Scrape every complex in complexes.yaml and write today's snapshots.

    python -m scraper.run                 # all complexes
    python -m scraper.run --only attain-chics-beach
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from . import appfolio, entrata, g5, realpage_craft, realpage_leasestar, rentcafe, sightmap
from .models import Snapshot

ROOT = Path(__file__).resolve().parent.parent
MODULES = {
    "realpage_craft": realpage_craft,
    "entrata": entrata,
    "rentcafe": rentcafe,
    "appfolio": appfolio,
    "sightmap": sightmap,
    "realpage_leasestar": realpage_leasestar,
    "g5": g5,
}

log = logging.getLogger("scraper")


def load_complexes() -> list:
    return yaml.safe_load((ROOT / "complexes.yaml").read_text())["complexes"]


def scrape_one(cfg: dict, today: date) -> Snapshot:
    module = MODULES[cfg["scraper"]]
    info, floorplans, units = module.scrape(cfg, today)
    if not floorplans:
        raise ValueError("No floorplans parsed")
    return Snapshot(
        slug=cfg["slug"],
        name=cfg["name"],
        url=cfg.get("website") or cfg["url"],
        scraped_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        property=info,
        floorplans=floorplans,
        units=units,
        price_basis=getattr(module, "PRICE_BASIS", "base"),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="slugs to scrape (default: all)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    today = date.today()
    out_dir = ROOT / "data" / "snapshots" / today.isoformat()
    status_path = ROOT / "data" / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}

    failures = 0
    for cfg in load_complexes():
        if args.only and cfg["slug"] not in args.only:
            continue
        started = time.time()
        try:
            snap = scrape_one(cfg, today)
        except Exception as e:
            failures += 1
            log.error("%s failed: %s", cfg["slug"], e)
            traceback.print_exc()
            status[cfg["slug"]] = {**status.get(cfg["slug"], {}), "last_attempt": today.isoformat(), "ok": False, "error": str(e)[:300]}
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{cfg['slug']}.json").write_text(json.dumps(snap.to_dict(), indent=1) + "\n")
        avail = sum(fp.units_available for fp in snap.floorplans)
        log.info("%s: %d floorplans, %d units available (%.1fs)", cfg["slug"], len(snap.floorplans), avail, time.time() - started)
        status[cfg["slug"]] = {"last_attempt": today.isoformat(), "last_success": today.isoformat(), "ok": True}

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, indent=1, sort_keys=True) + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
