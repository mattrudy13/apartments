#!/bin/bash
# Scrape all complexes on this machine and push the snapshot to GitHub.
# The sites block GitHub's servers, so scraping runs locally; pushing data/
# triggers the Action that rebuilds and deploys the Pages site.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${APARTMENTS_PYTHON:-$REPO/.venv/bin/python}"
cd "$REPO"
echo "=== $(date '+%F %T') scrape start ==="

git pull --rebase --autostash -q origin main || { echo "git pull failed"; exit 1; }
"$PYTHON" -m scraper.run
status=$?

git add data
if git diff --cached --quiet; then
  echo "no data changes"
else
  git commit -q -m "data: snapshot $(date +%F)" && git push -q origin main && echo "pushed"
fi
echo "=== $(date '+%F %T') done (scrape exit $status) ==="
exit $status
