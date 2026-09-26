#!/bin/zsh
# Unattended weekly refresh, run by launchd (Wednesday 16:00, Thursday 11:00).
# EIA posts the weekly spot prices on Wednesday; Thursday is the backup run.
#   1. build_charts.py pulls the EIA series and rewrites output/.
#   2. If the CSV changed: commit and push. GitHub Pages then serves the new
#      chart at data4thepeople.github.io/CrackSpreadCalc/output/crack_spread_321_weekly.html
# Success and failure each show a macOS alert box; details are in logs/weekly.log.
set -u
ROOT="${0:A:h:h}"
PY="$ROOT/.venv/bin/python"
LOG="$ROOT/logs/weekly.log"
URL="https://data4thepeople.github.io/CrackSpreadCalc/output/crack_spread_321_weekly.html"
mkdir -p "$ROOT/logs"
exec >>"$LOG" 2>&1
cd "$ROOT" || exit 1
echo "\n=== $(date '+%Y-%m-%d %H:%M %Z') ==="

# An alert box stays on screen until clicked; a banner notification can come
# and go unseen. "Open chart" opens the live page.
alert() {
  b=$(osascript -e "display alert \"$1\" message \"$2\" buttons {\"Open chart\", \"OK\"} default button \"OK\" giving up after 86400" 2>/dev/null)
  [[ "$b" == *"Open chart"* ]] && open "$URL"
}

fail() {
  echo "FAILED: $1"
  git checkout -q -- output 2>/dev/null
  alert "Crack spread weekly update failed" "$1. Details in logs/weekly.log."
  exit 1
}

git pull -q --rebase || fail "git pull"
"$PY" build_charts.py || fail "build_charts.py"

if git diff --quiet -- output/crack_spread_data.csv; then
  echo "no new week"; git checkout -q -- output; exit 0
fi

IFS=, read -r week ny gc wti < <(tail -1 output/crack_spread_data.csv)
git add output
git commit -q -m "Refresh crack spread with EIA week ending $week

Automatic weekly update (scripts/weekly.sh). NY 3-2-1 \$$ny, GC \$$gc, WTI \$$wti." || fail "git commit"
git push -q || fail "git push"
echo "pushed: week ending $week"
alert "Crack spread chart updated" "Week ending $week: NY 3-2-1 \$$ny, Gulf Coast \$$gc, WTI \$$wti. Live on GitHub Pages in a minute or two."
