# Apartment tracker — project notes

Tracks availability and pricing for a list of apartment complexes and publishes a
static dashboard to GitHub Pages: https://mattrudy13.github.io/apartments/
See README.md for usage commands.

## Status (2026-10-06)

Working end to end:
- Nine tracked complexes (`complexes.yaml`): Attain at Chic's Beach (`sightmap`, was
  `realpage_craft` until 2026-10-06),
  ReNew Marina Shores (`entrata`), Linkhorn Bay (`rentcafe`), North Beach (`appfolio`), and
  added 2026-10-06: Nexus (`sightmap`), Indigo 19 (`rentcafe`, no prices), North Hill
  (`realpage_leasestar`), Salt Meadow Bay (`rentcafe`, card layout) and Columbus Station (`g5`).
- Weekly launchd job on the Mac scrapes and pushes snapshots; the GitHub Action
  (`.github/workflows/deploy.yml`) tests, builds `site/data/` and deploys Pages.
- Overview page (`site/index.html`) and complex detail page (`site/complex.html?c=<slug>`).
- Effective (net) rent from specials, and per-unit listing history (see sections below).
- Real snapshots: `2026-10-04` (setup day; Linkhorn Bay and North Beach added that evening
  with `--only`) and `2026-10-05` (first scheduled Monday run, 09:00, all four OK and
  deployed). The scheduled job is confirmed working unattended. Next run: Mon 2026-10-12.
  The two snapshots are one day apart, so week-over-week trends start being meaningful
  after 2026-10-12.

Next steps: see ENHANCEMENTS.md (alerts are the top open item). Daily pulls are a one-liner
(`scripts/install_schedule.sh daily`) if wanted.

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

The original two sites block GitHub-hosted runners (tested 2026-10-05; Linkhorn Bay and
North Beach weren't tested there, and it doesn't matter since all scraping is local):
- Attain returns **403** to GitHub's IPs (works fine from the Mac with plain HTTP).
- ReNew's **Cloudflare challenge never clears** on the runner, even with real Chrome.

Don't try to work around this with proxies; the Mac-based schedule is the chosen design.

## The scheduler uses a separate clone (not this Desktop copy)

macOS privacy protection (TCC) blocks launchd jobs from reading `~/Desktop`
("Operation not permitted"), which covers this repo and its `.venv`.
So the launchd job runs from its own clone with its own venv:

- Clone: `~/Library/Application Support/apartments-scraper` (venv at `.venv/` inside it)
- Plist: `~/Library/LaunchAgents/com.apartments.scraper.plist`
- Log: `~/Library/Logs/apartments-scraper.log`
- Run now: `launchctl kickstart gui/$(id -u)/com.apartments.scraper`

The script runs `git pull` before every scrape, so changes pushed from this Desktop copy
(e.g. new entries in `complexes.yaml`) are picked up automatically. If `requirements.txt`
changes, reinstall deps in the clone's venv. Granting `bash` Full Disk Access was rejected
as too broad. The README documents this setup.

## Scraping load

Weekly volume is tiny (Attain: 1 request; ReNew: ~7 Chrome page loads over ~50 s; Linkhorn
Bay: 7 requests; North Beach: 2; Nexus: 3; Indigo 19: ~7; North Hill: 1 Chrome page load;
Salt Meadow Bay: ~7; Columbus Station: ~6 GraphQL POSTs). Only ReNew and North Hill use
Chrome. To fill in a newly added complex without re-hitting the others, run
`scraper.run --only <slug>` in the scheduler's clone and push (see README).
A random pause between ReNew detail pages is listed in ENHANCEMENTS.md but not done.

## Site quirks

**Attain (RealPage / Vest Craft template + Engrain SightMap)** — plain HTTP, scraper `sightmap`
- Since 2026-10-06 Attain is read from its **SightMap** (embed id `gow32268p2m`, JSON-escaped
  in the page data as `"sightmapEmbedUrl":"https:\/\/sightmap.com\/embed\/gow32268p2m"`).
  SightMap holds the live prices: base rent + total with required fees (~$135/mo), flat
  12-month pricing.
- Why: the page's embedded Vue `:units` data (the old `realpage_craft` source) was stale or
  wrong. 10 of 26 available units had different prices, and 4705 #104 was filed as a 1BR A3
  at $1,692 when SightMap (and the site's map) shows a 2BR B2.1 at $1,515 base / $1,650
  total. The user spotted it on the site.
- Building IDs differ between sources ("4705-WSH" vs "4705"; Haven Residences buildings are
  "1"/"2"/"3" in SightMap), so `complexes.yaml` sets `unit_history_since: 2026-10-06` for
  Attain. Unit tracking (new/gone/days listed) restarts there; the complex-level price trend
  keeps the older data.
- SightMap lists only plans; sqft/images for plans without units come from the page's
  embedded `:floorplans` data (names match after dropping the `-V`/`-H` suffix), and the
  phone from `:property`.
- `realpage_craft` is kept for other Vest/RealPage sites. Its notes still apply: the
  embedded data uses `floorPlanCode` (match units by code, not name), keeps only
  `unitAvailable: true`, and uses a `12/31/0000` placeholder date. Treat its prices as
  possibly stale; prefer a SightMap embed when the site has one.

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

**Nexus (Greystar site + Engrain SightMap)** — plain HTTP
- `/floorplans/` embeds `sightmap.com/embed/<id>`; that embed page names the data URL
  `sightmap.com/app/api/v1/<asset>/sightmaps/<n>` (public JSON; httpx handles its compression).
- Units have base `price`, `total_price` (list; includes required monthly fees),
  `display_lease_term` ("14 Months"), `available_on`, `building`, `specials_description`.
- Floor plan `name` is a JSON string (`{"name":"A1","provider_id":...}`); a `TEMP` placeholder
  plan is skipped. SightMap has no plan sqft, so plans without units take sqft from the page
  cards ("A0 / 1 bed / 1 bath / 563 sq. ft.").
- JSON-LD is wrapped in `@graph`; `entrata.parse_property` handles that.

**Indigo 19 (RentCafe, Greystar)** — plain HTTP, **no prices**
- Cards say "Call for Details" with no plan link; plan pages still exist at
  `/floorplans/<name-slug>` and list units as "Rent: Call" with no dates. The SecureCafe
  leasing site returns 403 to plain requests. Tracked for units/availability; price None,
  `priced: False`, shown as "Call".

**North Hill (RealPage LeaseStar, Greystar)** — Chrome
- Data API `api.ws.realpage.com/v2/property/8871769/{floorplans,units?available=true...}`
  returns 401 without a token the page's JS gets, so `realpage_leasestar` loads the page
  with `Browser.get_json_responses` and reads those responses.
- Units: `rent` (base), `totalRent` (incl. required fees), `minLeaseTermInMonth` (15),
  `floorNumber`, `vacantDate`. Plan-level `bedRooms` is wrong for some plans (B2 says 1, its
  units are 2-bed; the property is all 2BR), so when units contradict plans, plans without
  units fall back to the most common unit bed count.
- The site shows a stale banner special ("2 Weeks Base Rent Free When You Move In by May
  31st!"), which isn't scraped. It prompted the stale-date rule in `specials.py` (below).

**Salt Meadow Bay (RentCafe, card layout)** — plain HTTP
- Plan pages list units as cards (`#availApts .card`), not table rows:
  "Apartment: # 0837-210", "Available Now" / "Date Available: 11/2/2026", "Total Monthly
  Leasing Price Starting at: $2,373", "Base rent $2,333 · 9-month term". Cards without the
  "Total" label show only "Starting at" (treated as rent). `rentcafe.parse_units` falls back
  to this layout when there are no `tr.unit-container` rows.

**Columbus Station (G5 Marketing Cloud)** — plain HTTP
- Data from `inventory.g5marketingcloud.com/graphql` (no auth): `apartmentComplex(locationUrn)`
  for floorplans, then `units(floorplanId)` per plan with units. The `g5-cl-...` URN is in
  the page HTML. Queries in `g5.py` are trimmed copies of the site's; units limit raised
  from 9 to 100. Plans show a rate range even with 0 units (ignored when nothing's available).
- Apply URLs carry a widget tail (`&SearchUrl=...{widget.moveInDate...}`), trimmed.

## Verified browser behavior (ReNew's Cloudflare, from the Mac)

- Playwright's **bundled Chromium (headless) does NOT pass** — stuck on a Turnstile challenge.
- **Installed Google Chrome via `channel="chrome"` passes, both headed and headless.**
  `fetch.Browser` therefore prefers `channel="chrome"` and only falls back to bundled
  Chromium if Chrome isn't installed. Waits out "Just a moment..." titles (up to ~45s).
- A full ReNew scrape takes ~50s (listing page + one detail page per available plan).

## Price basis

- `Unit.price` is **base rent** wherever a site shows it; `Unit.total_price` holds a
  "total monthly" price (base + required monthly fees) when shown (Nexus, North Hill, Salt
  Meadow Bay). Entrata (ReNew) only shows the total, so its scraper declares
  `PRICE_BASIS = "total"`, saved as `Snapshot.price_basis`; snapshots from before that
  field existed get the basis from the scraper module at build time. The UI labels those
  prices "incl. fees".

## Specials and effective rent

- Scrapers store specials raw as `[{title, description}]` on floorplans (and units for
  RealPage `unitSpecials`), plus `lease_months` when the site states a term (ReNew: "15mo lease").
  Old snapshots stored plain title strings; `build.normalize_specials` handles both.
- `scraper/specials.py` parses text into terms (months/weeks free, $ off once or monthly,
  min lease, move-in-by date, sign-by/expiry date, "select units"). Parsing happens in
  `build.py`, so parser fixes apply retroactively to all snapshots.
- Deadlines without a year: a date >60 days past rolls to next year only if that lands within
  ~120 days ("Jan 15" seen in December); otherwise it stays in the past, so a stale banner
  ("May 31" in October) reads as ended.
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

- Overview trends are **small multiples**: one mini chart per complex, all on one shared
  y-scale, single accent color, with chips for Lowest price / Net of specials / Units. This
  replaced combined multi-line charts once there were more complexes (9) than palette colors (8).
- Detail-page charts use the dataviz skill's validated categorical palette (CSS vars
  `--series-1..8`, separate light/dark steps in `site/style.css`), in fixed order.
- Unpriced complexes/plans/units show "Call"; bedroom columns sort Studio, 1 BR, 2 BR, ...
- The overview table is sortable (Complex, Units, Lowest price, each bedroom column) and
  defaults to cheapest first. Price sorts use the net price when specials lower it;
  complexes with no price (or no units of that size) always sort last.
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

- Desktop copy: `~/Desktop/coding/GitHub/apartments`, venv at `.venv/` inside it (Python 3.9;
  activate with `source .venv/bin/activate`; code stays 3.9-compatible
  via `from __future__ import annotations`). CI uses Python 3.12.
- Local preview: `python build.py && python -m http.server -d site 8000`.
- Snapshots/data are committed only from the scheduler's clone (weekly job, or a manual
  `--only` run there); code changes come from this Desktop copy. Scraping in this copy
  is fine for testing, but discard `data/` changes before pulling.
- Test UI changes against real data plus fake earlier snapshots in a scratch copy of the
  repo (not in `data/`), then screenshot with Playwright in light/dark and at 390px width.
