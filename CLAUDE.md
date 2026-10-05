# Apartment tracker — project notes

Tracks availability and pricing for a list of apartment complexes and publishes a
static dashboard to GitHub Pages: https://mattrudy13.github.io/apartments/
See README.md for usage commands.

## Status (2026-10-04)

Working end to end:
- Scrapers for the four tracked complexes (`complexes.yaml`): Attain at Chic's Beach
  (`realpage_craft`), ReNew Marina Shores (`entrata`), Linkhorn Bay (`rentcafe`) and
  North Beach (`appfolio`).
- Weekly launchd job on the Mac scrapes and pushes snapshots; the GitHub Action
  (`.github/workflows/deploy.yml`) tests, builds `site/data/` and deploys Pages.
- Overview page (`site/index.html`) and complex detail page (`site/complex.html?c=<slug>`).
- First real snapshot: `data/snapshots/2026-10-04/`. Trend lines appear after the
  second weekly pull.

- Effective (net) rent from specials, and per-unit listing history (see sections below).

Possible next steps (see ENHANCEMENTS.md): add more complexes (a new platform needs a new `scraper/` module),
switch to daily pulls (`scripts/install_schedule.sh daily`).

## Layout

- `scraper/` — `models.py` (normalized schema), `fetch.py` (httpx + Playwright `Browser`,
  parse helpers), one module per platform exposing `scrape(cfg, today)`, `run.py` (CLI,
  writes `data/snapshots/<date>/<slug>.json` and `data/status.json`).
- `build.py` — aggregates snapshots into `site/data/summary.json` and `site/data/<slug>.json`
  (gitignored; CI regenerates it).
- `site/` — static vanilla JS + Chart.js (cdnjs); `app.js` serves both pages via `body[data-page]`.
- `tests/` — parser tests against saved HTML in `tests/fixtures/`. `pytest.ini` puts the repo
  root on the path (plain `pytest` failed in CI without it).
- `scripts/` — `scrape_and_push.sh` (pull → scrape → commit/push `data/`) and
  `install_schedule.sh` (launchd job `com.apartments.scraper`, Mondays 9:00).

## Why scraping runs on the Mac, not GitHub Actions

Both sites block GitHub-hosted runners (tested 2026-10-05):
- Attain returns **403** to GitHub's IPs (works fine from the Mac with plain HTTP).
- ReNew's **Cloudflare challenge never clears** on the runner, even with real Chrome.

Don't try to work around this with proxies; the Mac-based schedule is the chosen design.

## The scheduler uses a separate clone (not this Desktop copy)

macOS privacy protection (TCC) blocks launchd jobs from reading `~/Desktop`
("Operation not permitted"), which covers this repo and `~/Desktop/coding/GitHub/.venv`.
So the launchd job runs from its own clone with its own venv:

- Clone: `~/Library/Application Support/apartments-scraper` (venv at `.venv/` inside it)
- Plist: `~/Library/LaunchAgents/com.apartments.scraper.plist`
- Log: `~/Library/Logs/apartments-scraper.log`
- Run now: `launchctl kickstart gui/$(id -u)/com.apartments.scraper`

The script runs `git pull` before every scrape, so changes pushed from this Desktop copy
(e.g. new entries in `complexes.yaml`) are picked up automatically. If `requirements.txt`
changes, reinstall deps in the clone's venv. Granting `bash` Full Disk Access was rejected
as too broad. The README documents this setup.

## Site quirks

**Attain (RealPage / Vest Craft template)**
- All data is embedded in the homepage as HTML-escaped JSON Vue props:
  `:property`, `:floorplans`, `:units`. Plain HTTP with a browser User-Agent works.
- `:units` includes unavailable units (with prices); keep only `unitAvailable: true`.
  Unavailable units carry a placeholder date `12/31/0000` (parsed to `None`).
- Floorplan **names and codes differ slightly** (e.g. name `A4.1V`, code `A4.1-V`).
  Units reference `floorPlanCode`, so match units to floorplans **by code**, never by name.
- Sum of `numberUnitsAvailable` matched the count of available units (29) when verified.

**ReNew (Entrata, behind Cloudflare)**
- Configured `url` is the floorplans listing page (`/virginia-beach/renew-marina-shores/conventional/`).
  Each `.fp-card` gives name, beds/baths/sqft, specials, and min/max rent from the
  `.calculate-btn[data-url]` query string (`min_rent`, `max_rent`). Floorplan code = the
  numeric ID in the details URL (e.g. `douglas-690926`).
- **Cards undercount** availability ("Only 1 Unit Available!") compared with the detail
  pages, which list every unit including later move-in dates. The scraper visits each
  available plan's detail page (`.fp-units-table .option-row`, columns mapped from the
  header row) and uses the **detail-page unit count** and lowest unit price.
- **Unit numbers repeat across buildings** (there are three unit 110s, in buildings
  2200/2208/2221). A unit's identity is building + unit number; the UI shows the building.
- No floor data; the UI hides the Floor/Building columns when no unit has them.
- Address/phone come from the `ApartmentComplex` JSON-LD block.

**Linkhorn Bay (Yardi RentCafe)** — plain HTTP
- `/floorplans` has one `.fp-container` card per plan (code = numeric ID in
  `id="fp-container-602897"`), with "Starting at" price and "N Available". The count
  element has `data-max="6"`, so cards may cap the count; the scraper uses the number
  of unit rows on each plan's page (`/floorplans/the-birch`, `tr.unit-container`).
- Unit rent is a range ("$1,672 to $2,209", varies by lease term/move-in); the lowest is
  stored as the price. Lease term isn't stated, so net rent would assume 12 months.
- Floor comes from amenities ("Second Floor Unit"). Unit numbers like `502S12` are unique,
  so building is left empty.
- JSON-LD `@type` is a list (`["LocalBusiness", "ApartmentComplex"]`);
  `entrata.parse_property` (shared) accepts both forms.
- No specials listed when added (2026-10-04); only a generic "special offers valid for
  new residents" disclaimer.

**North Beach (AppFolio listings on a Duda site)** — plain HTTP
- The floor-plans page is static marketing text. Real data: the availability page's
  widget calls `/rts/collections/public/<siteAlias>/runtime/collection/appfolio-listings/query-data`;
  `siteAlias` (`d12fed8f`) is in the page HTML, so the scraper derives the endpoint.
- The collection holds the whole management company's account (Pembroke: 88 listings,
  6 properties); filter to this site by `portfolio_url`. Paged (`page.totalPages`).
- Each listing is a unit; floorplans are grouped by `unit_template_name`, so renovated
  and unrenovated versions ("Shore" vs "Shore (Renovated)") are separate plans. Only
  plans with listings appear (no unavailable plans).
- Unit numbers repeat across buildings (`#204` in several street addresses); building =
  street address, so the building + unit key keeps them distinct.
- No specials; fees in `fee_values` are optional pet fees only.

## Verified browser behavior (ReNew's Cloudflare, from the Mac)

- Playwright's **bundled Chromium (headless) does NOT pass** — stuck on a Turnstile challenge.
- **Installed Google Chrome via `channel="chrome"` passes, both headed and headless.**
  `fetch.Browser` therefore prefers `channel="chrome"` and only falls back to bundled
  Chromium if Chrome isn't installed. Waits out "Just a moment..." titles (up to ~45s).
- A full ReNew scrape takes ~50s (listing page + one detail page per available plan).

## Specials and effective rent

- Scrapers store specials raw as `[{title, description}]` on floorplans (and units for
  RealPage `unitSpecials`), plus `lease_months` when the site states a term (ReNew: "15mo lease").
  Old snapshots stored plain title strings; `build.normalize_specials` handles both.
- `scraper/specials.py` parses text into terms (months/weeks free, $ off once or monthly,
  min lease, move-in-by date, sign-by/expiry date, "select units"). Parsing happens in
  `build.py`, so parser fixes apply retroactively to all snapshots.
- Effective rent = (rent × lease − free months × rent − one-time $) ÷ lease − monthly $.
  Lease defaults to 12 months when unknown (flagged `lease_assumed`).
- A special is skipped (and the reason recorded) when: terms weren't understood, offer
  expired before the scrape date, the move-in deadline already passed, the quoted lease is
  shorter than its minimum, or **the unit's available date is after its move-in-by date**
  (checked per unit). "Select units" specials still apply but are flagged with `*`.
- ReNew today: "Two Months Free" on 12+ month leases, prices quoted for 15 months →
  net = 13/15 of listed (e.g. $1,944 → $1,685). Attain had no specials when built
  (`propertySpecialsAvailable: false`); its specials format is unverified, parsed defensively.

## Unit history

- `build.unit_histories` keys units by `building#unit_number` and tracks a listing streak:
  first seen, days listed, price changes. A unit that drops off and reappears starts a new
  streak. Units in the previous snapshot but not the latest are reported as `gone_units`.
- History only accrues from real snapshots (one per week), so "New"/price changes show
  up after the second pull.

## Design choices (frontend)

- Chart colors use the dataviz skill's validated categorical palette (CSS vars
  `--series-1..8`, separate light/dark steps in `site/style.css`), assigned in fixed
  order. Color follows the entity (complex order in `complexes.yaml`), not rank.
- Complex detail page charts **lowest price by bedroom count** (≤4 series) instead of
  one line per floorplan (Attain has 49 plans, which would be unreadable). Per-floorplan
  trends are sparklines in the floorplan table instead.
- One y-axis per chart: price and unit count are separate charts on the overview.
- Price deltas: up is red (bad for a renter), down is green; unit deltas the reverse.
- "Net" values appear only when specials lower the price (Net columns are hidden at a
  complex with none); charts have a Listed / Net toggle.
- Unit "Listed" age: units already present at the first pull show "—" on day zero and
  "N wk+" afterwards, since their true listing date is unknown.
- A complex whose latest scrape failed is flagged "stale" and keeps showing its last good data.

## Dev notes

- Desktop venv: `~/Desktop/coding/GitHub/.venv` (Python 3.9; code stays 3.9-compatible
  via `from __future__ import annotations`). CI uses Python 3.12.
- Local preview: `python build.py && python -m http.server -d site 8000`.
- Commit snapshots/data only via the scheduler; code changes from this copy.
