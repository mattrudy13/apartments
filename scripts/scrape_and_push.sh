#!/bin/bash
# Scrape all complexes on this machine and push the snapshot to GitHub.
# The sites block GitHub's servers, so scraping runs locally; pushing data/
# triggers the Action that rebuilds and deploys the Pages site. Then it emails the
# weekly digest (alerts.py; skipped until ~/.config/apartments/alerts.env exists).
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${APARTMENTS_PYTHON:-$REPO/.venv/bin/python}"
cd "$REPO"
echo "=== $(date '+%F %T') scrape start ==="

git pull --rebase --autostash -q origin main || {
  echo "git pull failed"
  "$PYTHON" alerts.py --send --failure "git pull failed, so nothing was scraped this week."
  exit 1
}
"$PYTHON" -m scraper.run
status=$?

problems=()
git add data
if git diff --cached --quiet; then
  echo "no data changes"
else
  if git commit -q -m "data: snapshot $(date +%F)" && git push -q origin main; then
    echo "pushed"
  else
    problems=(--problem "git push failed, so the site wasn't updated with this pull.")
  fi
fi

# The digest is a notification, so a mail problem is logged but doesn't fail the job.
"$PYTHON" alerts.py --send "${problems[@]+"${problems[@]}"}" || echo "digest email failed"
echo "=== $(date '+%F %T') done (scrape exit $status) ==="
exit $status
