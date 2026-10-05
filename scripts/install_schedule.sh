#!/bin/bash
# Install (or update) a macOS launchd job that runs scrape_and_push.sh weekly.
#   scripts/install_schedule.sh            # Mondays 9:00
#   scripts/install_schedule.sh daily      # every day 9:00
#   scripts/install_schedule.sh uninstall
# If the Mac is asleep at that time, launchd runs the job when it wakes.
set -euo pipefail

LABEL="com.apartments.scraper"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${APARTMENTS_PYTHON:-$REPO/.venv/bin/python}"
LOG="$HOME/Library/Logs/apartments-scraper.log"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [[ "${1:-}" == "uninstall" ]]; then
  rm -f "$PLIST"; echo "Removed $LABEL"; exit 0
fi
[[ -x "$PYTHON" ]] || { echo "Python not found at $PYTHON (set APARTMENTS_PYTHON)"; exit 1; }

if [[ "${1:-}" == "daily" ]]; then
  WHEN="<dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>"
else
  WHEN="<dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>"
fi

mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$REPO/scripts/scrape_and_push.sh</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>APARTMENTS_PYTHON</key><string>$PYTHON</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>$WHEN
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed $LABEL (${1:-weekly}). Log: $LOG"
echo "Run now: launchctl kickstart gui/$(id -u)/$LABEL"
