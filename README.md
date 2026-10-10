# apartments

Tracks availability and pricing for a list of apartment complexes. A weekly job on a
Mac scrapes each complex's site and pushes a snapshot to `data/snapshots/`; a GitHub
Action then rebuilds and publishes a static dashboard to GitHub Pages:
https://mattrudy13.github.io/apartments/

- **Viable units** (main page): every unit across complexes that fits `viable.yaml`
  (currently 1 or 2 BR under $1,900 a month), cheapest first, with what you'd pay per month
  (tap it for rent, fees and specials), $/sq ft, availability, days listed and price changes;
  viable count and cheapest per complex; viable-unit trends; and your **shortlist** of starred
  floorplans/units, with a share link to move it to another device
- **All units**: everything still tracked: a sortable table of units available, lowest price
  and lowest price per bedroom count, switchable between **base rent** and **total per month**
  (rent + required fees), with net-of-specials prices and change since the last pull, plus trend
  charts (one small chart per complex on a shared scale)
- **Complex page**: current specials and how they were read, floorplans (sortable,
  filterable by bedrooms, starred only, or **viable only**, which is on by default), price per
  sq ft, the units in each plan with net rent, days listed and price changes, units no longer
  listed, and price history by bedroom count

**Viable units** are set in `viable.yaml`: bedroom counts and a monthly limit. Monthly cost is
rent after specials plus the required monthly fees the site lists. Sites that don't list fees
(Linkhorn Bay, Columbus Station, North Beach) use rent after specials and are marked "fees not
listed", so their real cost is somewhat higher. Unpriced ("Call") units never count. Scraping
is unaffected: every unit is still pulled and kept.

"Net" rent spreads specials (e.g. two months free) over the lease, applying caveats such
as move-in-by dates per unit; see `scraper/specials.py`.

**Data checks**: the build flags a complex with a "check data" badge (and lists the reasons
on its page) when its latest data disagrees with itself: floorplan counts vs unit lists,
units missing prices, a >15% move in the lowest price or a unit's price since the last pull,
or availability collapsing. When you see it, verify on the complex's official site.

Currently tracked (Virginia Beach): Attain at Chic's Beach, ReNew Marina Shores, Linkhorn
Bay, North Beach, Nexus, Indigo 19 (no published prices), North Hill, Salt Meadow Bay and
Columbus Station.

## Weekly email digest

After each weekly run, `alerts.py` emails a digest of **viable units** (same `viable.yaml`
as the site), comparing each complex with its pull about a week earlier: **new viable units**,
units that became **newly viable** (a price cut or special brought them under the limit),
**price drops** in monthly cost, viable units that left or now cost too much, your **starred
floorplans/units** (opened up, price changed, no longer listed; starred items are reported
viable or not), **specials** that started or ended, and anything that **needs attention**
(failed scrapes, data checks, a failed git push). An email arrives every week even when
nothing changed, so a missing one means the Mac didn't run the job.

`alerts.yaml` holds the `shortlist` (paste the "Copy share link" from the shortlist card;
re-paste after starring more). Push changes to it, or to `viable.yaml`, like any other file.

Mail goes out over SMTP with credentials kept **outside the repo**:

```sh
mkdir -p ~/.config/apartments
cp alerts.env.example ~/.config/apartments/alerts.env
chmod 600 ~/.config/apartments/alerts.env   # then fill in SMTP_USER / SMTP_PASSWORD
```

For Gmail, `SMTP_PASSWORD` is an [app password](https://myaccount.google.com/apppasswords)
(needs 2-Step Verification), not your normal password. Until the file exists the step is
skipped. To check it:

```sh
python alerts.py --preview /tmp/digest.html   # look at it in a browser, no email
python alerts.py --send                       # send the digest for the latest pull now
```

## Adding a complex

Add an entry to `complexes.yaml`. The `scraper` must match the site's platform:

| scraper          | platform                                     | `url` to use              |
|------------------|----------------------------------------------|---------------------------|
| `realpage_craft` | RealPage / Vest sites with embedded unit data (can be stale; prefer `sightmap` if the site has a SightMap) | homepage |
| `entrata`        | Entrata sites (behind Cloudflare; uses Chrome) | the floorplans listing page |
| `rentcafe`       | Yardi RentCafe sites                          | the `/floorplans` page    |
| `appfolio`       | AppFolio listings widget (Duda-built sites)   | the availability page     |
| `sightmap`       | sites embedding an Engrain SightMap           | the page with the embed (e.g. `/floorplans/`) |
| `realpage_leasestar` | RealPage LeaseStar sites (uses Chrome)    | the floor-plans page      |
| `g5`             | G5 Marketing Cloud sites                      | the floor-plans page      |

Optional `banner:` reads a site-wide promo banner ("Move in by Oct 31 and enjoy $500 off
2-bedroom homes") from a page over plain HTTP: `url` (default: `website`) and an optional CSS
`selector`. Only text with an understood discount is kept, and it lowers net rent like a
floorplan special (expired offers are shown as ended). Banners drawn by JavaScript aren't seen.

RentCafe sites come in two unit layouts (table rows or cards); both are handled. Some
sites publish no prices ("Rent: Call"); they're tracked for units and availability and
show "Call" instead of a price.

Prices are **base rent** wherever a site shows it; a site's "total monthly" price (rent plus
required monthly fees) is stored as `total_price` and shown beside it. Entrata sites only
show the total, so those prices are marked "incl. fees".

If a site switches data source and its unit IDs change, set `unit_history_since: "YYYY-MM-DD"`
on its entry so unit tracking (new/gone/days listed) restarts cleanly from that date.

A site on a different platform needs a new module in `scraper/` exposing
`scrape(cfg, today) -> (PropertyInfo, [FloorPlan], [Unit])`, registered in `scraper/run.py`,
plus a parser test against a saved copy of the page in `tests/fixtures/`.

After pushing the new entry, fill it in without re-scraping the other complexes by
running just that one in the scheduler's clone (see [Schedule](#schedule)):

```sh
cd ~/Library/Application\ Support/apartments-scraper && git pull
.venv/bin/python -m scraper.run --only <slug>
git add data && git commit -m "data: add <slug>" && git push
```

Otherwise it shows as "stale" until the next weekly run.

## Running locally

```sh
pip install -r requirements.txt
python -m playwright install chromium   # fallback if Google Chrome isn't installed
pytest -q                               # parser tests against saved pages
python -m scraper.run                   # writes data/snapshots/<today>/*.json
python build.py                         # writes site/data/*.json
python -m http.server -d site 8000      # open http://localhost:8000
```

To just view the latest data, skip the scrape: `git pull`, `python build.py`, then serve.
Scraping from this copy writes snapshot files that the scheduler also writes; discard
them before pulling (`git checkout data/`) so they don't conflict.

## Schedule

The apartment sites block GitHub's servers (Attain returns 403; ReNew's Cloudflare
check never clears), so scraping runs on a Mac and pushes the snapshot. Pushes to `main`
that touch `data/`, `site/`, `scraper/`, `tests/`, `build.py` or `complexes.yaml` redeploy
the site (docs-only changes don't); a failing test blocks the deploy.

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
keeps showing its last good data. Errors are recorded in `data/status.json` and listed at
the top of the weekly email.
