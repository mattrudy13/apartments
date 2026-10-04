# apartments

Tracks availability and pricing for a list of apartment complexes. A weekly GitHub
Action scrapes each complex's site, commits a snapshot to `data/snapshots/`, and
publishes a static dashboard to GitHub Pages:

- **Overview**: units available, lowest price, change since the last pull, and history charts
- **Complex page**: floorplans (sortable/filterable), units in each plan, price history by bedroom count

## Adding a complex

Add an entry to `complexes.yaml`. The `scraper` must match the site's platform:

| scraper          | platform                                     | `url` to use              |
|------------------|----------------------------------------------|---------------------------|
| `realpage_craft` | RealPage / Vest sites with embedded unit data | homepage                  |
| `entrata`        | Entrata sites (behind Cloudflare; uses Chrome) | the floorplans listing page |

A site on a different platform needs a new module in `scraper/` exposing
`scrape(cfg, today) -> (PropertyInfo, [FloorPlan], [Unit])`, registered in `scraper/run.py`.

## Running locally

```sh
pip install -r requirements.txt
python -m playwright install chromium   # fallback if Google Chrome isn't installed
pytest -q                               # parser tests against saved pages
python -m scraper.run                   # writes data/snapshots/<today>/*.json
python build.py                         # writes site/data/*.json
python -m http.server -d site 8000      # open http://localhost:8000
```

## Schedule

`.github/workflows/scrape.yml` runs Mondays at 13:00 UTC and on demand
(Actions → Scrape apartments → Run workflow). For daily pulls change the cron to
`0 13 * * *`. Enable Pages once under Settings → Pages → Source: **GitHub Actions**.

If a site fails to scrape, the run still publishes; that complex is marked
**stale** and keeps showing its last good data. Errors are recorded in `data/status.json`.
