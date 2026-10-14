#!/bin/bash
# Scrape all complexes on this machine and push the snapshot to GitHub.
# The sites block GitHub's servers, so scraping runs locally; pushing data/
# triggers the Action that rebuilds and deploys the Pages site. Then it emails the
# weekly digest (alerts.py; skipped until ~/.config/apartments/alerts.env exists).
#   scrape_and_push.sh           # every complex (Mondays 9:00)
#   scrape_and_push.sh --retry   # only complexes that failed earlier today (Mondays 14:00);
#                                # re-sends the digest only if it recovered one
set -uo pipefail
RETRY=""
[[ "${1:-}" == "--retry" ]] && RETRY="--retry"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${APARTMENTS_PYTHON:-$REPO/.venv/bin/python}"
cd "$REPO"
echo "=== $(date '+%F %T') scrape start ${RETRY} ==="

git pull --rebase --autostash -q origin main || {
  echo "git pull failed"
  # The morning run already emailed; a failed retry just waits for next week.
  [[ -n "$RETRY" ]] && exit 1
  "$PYTHON" alerts.py --send --failure "git pull failed, so nothing was scraped this week."
  exit 1
}
"$PYTHON" -m scraper.run $RETRY
status=$?

problems=()
git add data
# New snapshot files mean the retry recovered at least one complex.
recovered=$(git diff --cached --name-only --diff-filter=A -- data/snapshots)
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
# A retry that recovered nothing stays quiet: the morning digest already named the failures.
if [[ -z "$RETRY" || -n "$recovered" ]]; then
  "$PYTHON" alerts.py --send $RETRY "${problems[@]+"${problems[@]}"}" || echo "digest email failed"
fi
echo "=== $(date '+%F %T') done (scrape exit $status) ==="
exit $status
