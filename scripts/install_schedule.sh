#!/bin/bash
# Install (or update) the macOS launchd jobs that run scrape_and_push.sh weekly.
#   scripts/install_schedule.sh            # Mondays 9:00, retry of failures 14:00
#   scripts/install_schedule.sh daily      # every day 9:00, retry 14:00
#   scripts/install_schedule.sh uninstall
# If the Mac is asleep at that time, launchd runs the job when it wakes. The retry is a
# separate job because launchd can't pass different arguments per start time; it only
# re-scrapes complexes that failed earlier the same day (the Mac sleeping mid-run on
# 2026-10-12, a holiday, timed out three of them).
set -euo pipefail

LABEL="com.apartments.scraper"
RETRY_LABEL="$LABEL.retry"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${APARTMENTS_PYTHON:-$REPO/.venv/bin/python}"
LOG="$HOME/Library/Logs/apartments-scraper.log"

for label in "$LABEL" "$RETRY_LABEL"; do
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
done
if [[ "${1:-}" == "uninstall" ]]; then
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist" "$HOME/Library/LaunchAgents/$RETRY_LABEL.plist"
  echo "Removed $LABEL and $RETRY_LABEL"; exit 0
fi
[[ -x "$PYTHON" ]] || { echo "Python not found at $PYTHON (set APARTMENTS_PYTHON)"; exit 1; }

# when <hour>: the StartCalendarInterval dict for that hour (Mondays, or daily)
when() {
  local day=""
  [[ "${MODE}" == "daily" ]] || day="<key>Weekday</key><integer>1</integer>"
  echo "<dict>${day}<key>Hour</key><integer>$1</integer><key>Minute</key><integer>0</integer></dict>"
}

# install <label> <hour> [script args...]
install() {
  local label="$1" hour="$2"; shift 2
  local plist="$HOME/Library/LaunchAgents/$label.plist" args=""
  for a in "$REPO/scripts/scrape_and_push.sh" "$@"; do args+="<string>$a</string>"; done
  mkdir -p "$(dirname "$plist")"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>$args</array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>APARTMENTS_PYTHON</key><string>$PYTHON</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>$(when "$hour")
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST
  launchctl bootstrap "gui/$(id -u)" "$plist"
}

MODE="${1:-weekly}"
install "$LABEL" 9
install "$RETRY_LABEL" 14 --retry
echo "Installed $LABEL (9:00) and $RETRY_LABEL (14:00), ${MODE}. Log: $LOG"
echo "Run now: launchctl kickstart gui/$(id -u)/$LABEL"
