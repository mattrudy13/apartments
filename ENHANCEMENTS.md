# Enhancements

Ideas for the site, roughly in priority order within each section. `[~]` = partly done.
Finished items move to **Done** at the bottom.

## Comparison
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
- [ ] **Indigo 19 prices** — its own site says "Rent: Call" and its leasing portal blocks
      plain requests. Check other public sources that list its units with prices (e.g. the
      manager's site or a listing site) before giving up on it.
- [ ] **RentCafe behind Cloudflare** — since 2026-10-10 Linkhorn Bay, Salt Meadow Bay and
      Indigo 19 return a Cloudflare challenge to plain HTTP and headless Chrome. First find out
      whether it's the Mac's new network (test from a hotspot); only if it's Yardi-wide, try
      headed Chrome or another public source for those listings.
- [ ] **Say why a scrape failed** — record "blocked (Cloudflare challenge / 403 / 429)" vs "page
      changed (parse error)" in `status.json`, plus the network the run came from, and show it
      in the digest and the stale badge. Blocks are usually temporary; parse errors need code.
- [ ] **Fewer ReNew term requests** — ReNew rate-limits (429 on 2026-10-10). Fetch lease terms
      only for units whose bed count is in `viable.yaml` (or skip plans already far over the
      limit), cutting ~28 requests a week. Verify the first scheduled run (2026-10-12) first.
- [ ] **Starred floorplans survive source switches** — shortlist floorplan ids use the site's
      plan code, which changed when North Hill moved to SightMap. Fall back to matching by
      complex + plan name so stars carry over.
- [ ] **Digest: don't count term switches as price drops** — the first run after lease-term
      pricing (and any week the cheapest term changes) can report "drops" that are only a
      different lease length. Compare at the same term when both pulls have it, or label it.
- [ ] **Target move-in date** — SightMap and Entrata price by move-in date; the scraper asks for
      each unit's available date. A move-in date in `viable.yaml` would price every unit for when
      you'd actually move (and could hide units not available by then).
- [ ] **Banners shown by JavaScript** — site-wide banners are read from static HTML only
      (Attain, North Hill). Some sites show promos in JS popups (Greystar/Nexus, G5/Columbus
      Station, North Hill's "Special Offers" pop-up); reading those needs Chrome per site.

## Polish
- [ ] **Floorplan image lightbox** — image URLs are scraped; only thumbnails are shown.
- [ ] **Map view** of complexes (lat/long available for most).
- [ ] **Pet-friendly filter** — Columbus Station splits plans by pet policy ("Pet Friendly" vs
      "Not Pet Friendly"); North Beach lists cats/dogs per unit.

## Done
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
