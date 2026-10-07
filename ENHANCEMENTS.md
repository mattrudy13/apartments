# Enhancements

Ideas for the site, roughly in priority order. `[x]` done, `[~]` partly done.

## High value
- [ ] **Price-drop / new-unit alerts** — the weekly job already diffs snapshots; notify
      (email or ntfy.sh / Pushover) when a unit drops below a target price or a watched
      floorplan becomes available.
- [x] **Effective rent with specials** — e.g. ReNew's "Two Months Free" on a 15-mo lease is
      ~13% off. Show net monthly rent beside the listed price. Specials text is already
      scraped; needs parsing into months-free / lease length.
- [x] **Unit-level history** — snapshots store every unit: show days on market and price
      changes per unit ("listed 5 weeks, dropped twice").

## Comparison
- [ ] **Price per sq ft** column and sort.
- [ ] **Cross-complex search page** — one table of all available units, filterable by beds,
      max price and move-in date.
- [ ] **Shortlist** — star floorplans/units and see them on the overview (localStorage).

## Data & reliability
- [~] **"New this week" / "gone" badges** — partly done: units show a "New" badge and the
      complex page lists units no longer listed. Still open: surface new/gone counts on the
      overview.
- [~] **Scrape-health indicator** — partly done: a complex whose latest scrape failed shows
      "stale". Still open: last successful pull per complex on the overview, and a warning if
      the weekly job hasn't pushed in 8+ days (Mac off, or a site changed).
- [ ] **Gentler ReNew scraping** — add a random 5–10 s pause between ReNew's detail pages
      (Cloudflare-protected; currently back to back). Not urgent at weekly volume.
- [ ] **Floorplan image lightbox** — image URLs are already scraped; only thumbnails shown now.

## Polish
- [ ] **Map view** of complexes (Attain's data includes lat/long).
- [ ] **Lease-term pricing** — ReNew's prices are for 15-mo leases; Linkhorn Bay shows a
      per-unit rent range (e.g. $1,672–$2,209) that likely varies by term, and we store the
      low end. Capture terms where sites expose them before trusting cross-complex comparisons.
- [x] **More than 8 complexes** — the overview's trend charts are small multiples (one
      card per complex, shared scale), so the list can grow without running out of colors.
