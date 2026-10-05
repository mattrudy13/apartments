# Enhancements

Ideas for the site, roughly in priority order. Check off as done.

## High value
- [ ] **Price-drop / new-unit alerts** — the weekly job already diffs snapshots; notify
      (email or ntfy.sh / Pushover) when a unit drops below a target price or a watched
      floorplan becomes available.
- [ ] **Effective rent with specials** — e.g. ReNew's "Two Months Free" on a 15-mo lease is
      ~13% off. Show net monthly rent beside the listed price. Specials text is already
      scraped; needs parsing into months-free / lease length.
- [ ] **Unit-level history** — snapshots store every unit: show days on market and price
      changes per unit ("listed 5 weeks, dropped twice").

## Comparison
- [ ] **Price per sq ft** column and sort.
- [ ] **Cross-complex search page** — one table of all available units, filterable by beds,
      max price and move-in date.
- [ ] **Shortlist** — star floorplans/units and see them on the overview (localStorage).

## Data & reliability
- [ ] **"New this week" / "gone" badges** on units, from diffing against the previous snapshot.
- [ ] **Scrape-health indicator** — last successful pull per complex, plus a warning if the
      weekly job hasn't pushed in 8+ days (Mac off, or a site changed).
- [ ] **Floorplan image lightbox** — image URLs are already scraped; only thumbnails shown now.

## Polish
- [ ] **Map view** of complexes (Attain's data includes lat/long).
- [ ] **Lease-term pricing** — ReNew's prices are for 15-mo leases; detail pages may list
      other terms. Verify before trusting cross-complex comparisons.
