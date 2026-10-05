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

The apartment sites block GitHub's servers (Attain returns 403; ReNew's Cloudflare
check never clears), so scraping runs on a Mac and pushes the snapshot:

```sh
scripts/install_schedule.sh          # launchd job: Mondays 9:00 (runs on wake if asleep)
scripts/install_schedule.sh daily    # every day 9:00
scripts/install_schedule.sh uninstall
launchctl kickstart gui/$(id -u)/com.apartments.scraper   # run it now
tail -f ~/Library/Logs/apartments-scraper.log
```

The job uses `.venv/bin/python` in the repo unless `APARTMENTS_PYTHON` is set when
installing.

**Run the scheduler from a clone outside `~/Desktop`, `~/Documents` or `~/Downloads`.**
macOS privacy protection blocks launchd jobs from reading those folders ("Operation
not permitted"). The current setup uses a dedicated clone with its own venv:

```sh
D="$HOME/Library/Application Support/apartments-scraper"
git clone https://github.com/mattrudy13/apartments.git "$D"
/usr/bin/python3 -m venv "$D/.venv"
"$D/.venv/bin/pip" install -r "$D/requirements.txt"
"$D/scripts/install_schedule.sh"
```

The job pulls before each run, so changes pushed from any other copy (e.g. new entries
in `complexes.yaml`) are picked up automatically. If `requirements.txt` changes, rerun the
`pip install` line above. Each push to `data/` triggers `.github/workflows/deploy.yml`, which runs
the tests, rebuilds `site/data/` and deploys Pages
(https://mattrudy13.github.io/apartments/).

If a site fails to scrape, the run still pushes; that complex is marked **stale** and
keeps showing its last good data. Errors are recorded in `data/status.json`.
