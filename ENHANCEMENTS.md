# Enhancements

Ideas for the site, roughly in priority order within each section. `[~]` = partly done.
Finished items move to **Done** at the bottom.

## High value
- [ ] **Price-drop / new-unit alerts** — the weekly job already diffs snapshots; notify
      (ntfy.sh / Pushover / email) when a unit drops below a target price, a watched floorplan
      opens up, or a scrape fails. Could run as a step at the end of `scrape_and_push.sh`.
- [ ] **Data sanity checks** — Attain's embedded data was quietly wrong (stale prices, a 2BR
      filed as a 1BR) until it was noticed on the site. At build time, flag a complex when:
      card counts disagree with unit rows, a plan's "from" price is below every unit's
      price, units outside the plan's bed count, prices jump >15% week over week, or the unit
      count drops to 0. Show a "check data" badge and list the reasons on the complex page.
- [ ] **Compare by total monthly cost** — prices are base rent, but required fees vary
      (Attain ~$135/mo, Salt Meadow ~$40, North Hill ~$26, ReNew only shows totals). Add a
      "Total/mo" sort/toggle on the overview, using the total where a site gives it and
      marking complexes where it's unknown.

## Comparison
- [ ] **Cross-complex search page** — one table of all available units, filterable by beds,
      max price (base or total), move-in date and pet-friendly; sortable by price per sq ft.
- [ ] **Price per sq ft** column and sort (on the search page and floorplan tables).
- [ ] **Lease-term normalization** — prices are quoted for different terms: Attain 12 mo
      (flat), Nexus 14, North Hill and ReNew 15, Salt Meadow 9–15 per unit, Linkhorn Bay a
      range by term (we store the low end). Show the term next to prices and capture
      per-term prices where a site exposes them (SightMap's leasing price URL, RentCafe ranges).
- [ ] **Shortlist** — star floorplans/units and see them on the overview (localStorage).
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
- [ ] **Site-wide promo banners** — some specials live only in a page banner (North Hill's
      "2 Weeks Base Rent Free When You Move In by …"), not in floorplan/unit data. Scrape the
      banner text per site so net rent can use it (the stale-date rule already guards old ones).
- [ ] **Prefer live sources** — after Attain, check each site for a SightMap (or similar live
      widget) and prefer it over embedded page data; note per complex which source is used.
- [ ] **Gentler Chrome scraping** — a random 5–10 s pause between ReNew's detail pages
      (Cloudflare-protected; currently back to back). Not urgent at weekly volume.

## Polish
- [ ] **Floorplan image lightbox** — image URLs are scraped; only thumbnails are shown.
- [ ] **Map view** of complexes (lat/long available for most).
- [ ] **Pet-friendly filter** — Columbus Station splits plans by pet policy ("Pet Friendly" vs
      "Not Pet Friendly"); North Beach lists cats/dogs per unit.

## Done
- [x] **Effective rent with specials** — net rent spread over the lease, with move-in-by,
      expiry, minimum-lease and "select units" caveats; stale no-year deadlines read as ended.
- [x] **Unit-level history** — days listed, price changes, "New" badge, units no longer listed.
- [x] **More than 8 complexes** — overview trends are small multiples on a shared scale.
- [x] **Sortable overview** — cheapest first by default; price columns sort by net price.
- [x] **Base vs total pricing** — base rent everywhere a site shows it, total with fees
      stored and shown alongside; Entrata's total-only prices marked "incl. fees".
- [x] **Sites without prices** — tracked for units/availability, shown as "Call".
