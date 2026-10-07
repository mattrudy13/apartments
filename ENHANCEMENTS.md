# Enhancements

Ideas for the site, roughly in priority order within each section. `[~]` = partly done.
Finished items move to **Done** at the bottom.

## High value
- [ ] **Price-drop / new-unit alerts** — the weekly job already diffs snapshots; notify
      (ntfy.sh / Pushover / email) when a unit drops below a target price, a watched floorplan
      opens up, or a scrape fails. Could run as a step at the end of `scrape_and_push.sh`.

## Comparison
- [ ] **Cross-complex search page** — one table of all available units, filterable by beds,
      max price (base or total), move-in date and pet-friendly; sortable by price per sq ft.
- [ ] **Lease-term normalization** — prices are quoted for different terms: Attain 12 mo
      (flat), Nexus 14, North Hill and ReNew 15, Salt Meadow 9–15 per unit, Linkhorn Bay a
      range by term (we store the low end). Show the term next to prices and capture
      per-term prices where a site exposes them (SightMap's leasing price URL, RentCafe ranges).
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
- [ ] **Banners shown by JavaScript** — site-wide banners are read from static HTML only
      (Attain, North Hill). Some sites show promos in JS popups (Greystar/Nexus, G5/Columbus
      Station, North Hill's "Special Offers" pop-up); reading those needs Chrome per site.
- [ ] **Prefer live sources** — after Attain, check each site for a SightMap (or similar live
      widget) and prefer it over embedded page data; note per complex which source is used.

## Polish
- [ ] **Floorplan image lightbox** — image URLs are scraped; only thumbnails are shown.
- [ ] **Map view** of complexes (lat/long available for most).
- [ ] **Pet-friendly filter** — Columbus Station splits plans by pet policy ("Pet Friendly" vs
      "Not Pet Friendly"); North Beach lists cats/dogs per unit.

## Done
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
