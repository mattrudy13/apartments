# Enhancements

Ideas for the site, roughly in priority order within each section. `[~]` = partly done.
Finished items move to **Done** at the bottom.

## Comparison
- [ ] **Target move-in date** — SightMap and Entrata price by move-in date; the scraper asks for
      each unit's available date. A move-in date in `viable.yaml` (early Feb 2027) would price
      every unit for when you'd actually move, and mark or hide units a complex won't hold that
      long. On 2026-11-09, 77 of 103 viable units were available before January and only 15 were
      dated February or later (all Linkhorn Bay). Specials whose move-in deadline falls before the
      target date shouldn't count toward net rent either (Attain's banners end within weeks).
- [ ] **How far ahead each complex lists** — from the stored available dates, work out each
      complex's usual lead time (days between a unit first appearing and its available date) and
      how long units stay listed. That gives a "start looking seriously around <date>" per
      complex for a February move, instead of guessing from today's list.
- [ ] **Price by move-in month** — the main page compares units available now with ones months
      out. Group or filter the viable list by available month, and show whether later dates are
      priced higher or lower at each complex.
- [~] **Cross-complex search page** — done: the main page lists every viable unit across
      complexes (viable.yaml), sortable incl. $/sq ft, with a bedroom filter. Open: move-in
      date and pet-friendly filters, and an on-page way to adjust the limit.
- [ ] **Commute / distance** — distance or drive time from each complex to places you care
      about (work, beach). Most sites' JSON-LD or SightMap data includes lat/long.

## Data & reliability
- [~] **Scrape-health indicator** — done: a complex whose latest scrape failed shows
      "stale". Open: last successful pull per complex on the overview, and a site-wide warning
      if the weekly job hasn't pushed in 8+ days (Mac off, or a site changed).
- [~] **New / gone units on the overview** — done on complex pages ("New" badge, units no
      longer listed). Open: "+3 new / −2 gone" counts per complex in the overview table.
- [ ] **Show how each new special was read** — a misread banner lowered Attain's net rent by
      $155–190/mo for two pulls before anyone noticed (2026-11-11: "$500 off 1 & 2-bedroom OR one
      month free on 3-bedroom" applied both to every size). When a special's text is new, have the
      digest print the text next to "read as: ..." so a wrong reading is caught the first week.
      Also flag as uncertain any special with an "or" between two offers, or more than one
      discount type, and add a data check when specials cut a unit's rent by more than ~10%.
- [ ] **Date parsing before Python 3.15** — `specials._parse_loose_date` parses "Nov 30" with no
      year, which 3.14 warns about (38 warnings in the tests) and 3.15 will change or reject.
      Add the reference year to the text before parsing. Small; do it before upgrading Python.
- [ ] **Run CI on the Mac's Python** — CI tests on 3.12, the scraper runs on 3.14. Test both so
      a version difference shows up in CI, not on a Monday run.
- [ ] **Linkhorn Bay's price range** — it lists "$1,672 to $2,209" by lease term and move-in
      date; only the low end is stored, and it has 53 of the 98 viable units. Store the high end
      too and show the range, so its units aren't ranked on a price you may not be offered.
- [ ] **Available date changes** — a unit whose available date moves (pushed back, or back on
      the market sooner) isn't tracked; only price changes are. Record it in unit history and
      report it for starred units.
- [ ] **Say why a scrape failed** — record "blocked (Cloudflare challenge / 403 / 429)" vs "page
      changed (parse error)" vs "timed out" in `status.json`, plus the network the run came from
      and whether the Mac was on battery / lid closed (10-12's timeouts were the Mac sleeping, found
      only via `pmset -g log`). Show it in the digest and the stale badge. Blocks are usually
      temporary; parse errors need code; sleep needs nothing.
- [ ] **Fewer ReNew page loads** — only if ReNew is challenged on a *page load* again (10-13's
      runs were; 10-19's passed every page load, and only the 6th of 6 term requests got a 429). Skip detail pages for plans whose card price is far over the limit
      (~7 loads to ~4). Trade-off: those plans' units drop out of the All units page and history.
- [ ] **Starred floorplans survive source switches** — shortlist floorplan ids use the site's
      plan code, which changed when North Hill moved to SightMap. Fall back to matching by
      complex + plan name so stars carry over.
- [ ] **Digest: don't count term switches as price drops** — the first run after lease-term
      pricing (and any week the cheapest term changes) can report "drops" that are only a
      different lease length. Compare at the same term when both pulls have it, or label it.
- [ ] **Banners shown by JavaScript** — site-wide banners are read from static HTML only
      (Attain, North Hill). Some sites show promos in JS popups (Greystar/Nexus, G5/Columbus
      Station, North Hill's "Special Offers" pop-up); reading those needs Chrome per site.

## Polish
- [ ] **Floorplan image lightbox** — image URLs are scraped; only thumbnails are shown.
- [ ] **Map view** of complexes (lat/long available for most).
- [ ] **Pet-friendly filter** — Columbus Station splits plans by pet policy ("Pet Friendly" vs
      "Not Pet Friendly"); North Beach lists cats/dogs per unit.

## Done
- [x] **Per-bedroom banner offers** (2026-11-11) — free months can be tied to bedroom counts
      (`beds_free`), size lists like "1 & 2-bedroom" are read, and "moved in by" counts as a
      move-in deadline. Fixed Attain's Nov 2 banner (8 viable units to 3).
- [x] **Indigo 19 prices** — its own site has posted prices since 2026-11-02 (from $1,575), so no
      other source is needed. Its lease term isn't stated; net rent would assume 12 months.
- [x] **RentCafe in headless Chrome** (2026-11-02) — all three RentCafe sites got 403 challenges
      to plain requests; they now load through `fetch.Browser`. First scheduled run passed 11-09.
- [x] **90-day lows and latest move-in** (2026-10-19) — the All units table shows each bedroom
      size's lowest price over the last 90 days of pulls (same mode as the cell, plus net when
      lower) and each complex's furthest-out available date; complex pages show each plan's low.
      Lows start at `unit_history_since`.
- [x] **Lease-term normalization** — SightMap and Entrata (ReNew) prices for every term are
      scraped; each unit uses its cheapest term of 11+ months (`viable.yaml`), ties to the
      shorter lease, with all terms on tap. Not possible yet: RentCafe (Linkhorn Bay's range,
      Salt Meadow's single terms), AppFolio, G5 publish no per-term prices.
- [x] **Prefer live sources** — checked every site (2026-10-10): North Hill moved to its
      SightMap; Columbus Station's G5 page has an empty SightMap slot; RentCafe sites and ReNew
      have none. Complex pages show their data source.
- [x] **Viable-units focus** — `viable.yaml` (1–2 BR under $1,900/mo incl. listed fees, net of
      specials) drives the main page, complex pages' default filter and the email digest; the
      full overview moved to an "All units" page.
- [x] **Price-drop / new-unit alerts** — weekly email digest (`alerts.py`, last step of
      `scrape_and_push.sh`): new units, price drops, units newly under target prices, starred
      floorplans/units via a pasted shortlist link, specials started/ended, failed scrapes and
      data checks. Configured in `alerts.yaml`; SMTP creds in `~/.config/apartments/alerts.env`.
- [x] **Site-wide promo banners** — `banner:` in complexes.yaml (Attain, North Hill); discounts
      read from banner text lower net rent with the usual guards, incl. per-bedroom amounts
      ("$500 off 2-bedroom or $1,000 off 3-bedroom"). Tap a special for its full text.
- [x] **Afternoon retry** — a Mon 14:00 launchd job re-scrapes only that day's failures and
      re-sends the digest if it recovered one (2026-10-13, after the Mac slept through 10-12).
- [x] **Fewer ReNew term requests** — terms fetched after every page (a 429 costs only terms)
      and only for possibly viable units, ~28 requests to ~10 (2026-10-13; unverified live).
- [x] **RentCafe Cloudflare block** — Linkhorn Bay, Salt Meadow Bay and Indigo 19 were challenged
      2026-10-10 from a new network; it cleared by 10-12 with no changes. Nothing built.
- [x] **Gentler Chrome scraping** — random 5–10 s pause between Chrome page loads (ReNew ~80 s).
- [x] **Price per sq ft** — sortable column in floorplan tables, per unit, and in the shortlist
      (listed price; net in the tooltip). Add it to the search page when that's built.
- [x] **Shortlist** — star floorplans/units (localStorage), Shortlist card on the overview,
      "Starred only" filter on complex pages, share link to copy the list to another device.
- [x] **Effective rent with specials** — net rent spread over the lease, with move-in-by,
      expiry, minimum-lease and "select units" caveats; stale no-year deadlines read as ended.
- [x] **Unit-level history** — days listed, price changes, "New" badge, units no longer listed.
- [x] **More than 8 complexes** — overview trends are small multiples on a shared scale.
- [x] **Sortable overview** — cheapest first by default; price columns sort by net price.
- [x] **Base vs total pricing** — base rent everywhere a site shows it, total with fees
      stored and shown alongside; Entrata's total-only prices marked "incl. fees".
- [x] **Sites without prices** — tracked for units/availability, shown as "Call".
- [x] **Data sanity checks** — "check data" badge + reasons when a complex disagrees with
      itself: plan counts vs unit lists, units missing prices, >15% lowest-price or unit-price
      moves, availability dropping to 0 or by >60%. Never compares across bedroom counts
      (a 2BR below a 1BR is normal).
- [x] **Compare by total monthly cost** — "Base rent / Total per month" switch on the overview;
      totals net of specials, and sites without listed fees fall back to base, marked.
