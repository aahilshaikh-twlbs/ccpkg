#!/usr/bin/env bash
set -e
if ! pgrep -fl "iTerm" >/dev/null 2>&1; then
  echo "SKIP: iTerm not running"; exit 0
fi
PROBE=/tmp/ccpkg_swarm_iterm_smoke.$$
osascript <<EOF
tell application "iTerm"
  tell current window
    set newTab to (create tab with default profile)
    tell current session of newTab
      write text "echo SMOKE > $PROBE; sleep 1; exit"
    end tell
  end tell
end tell
EOF
for i in $(seq 1 6); do sleep 1; [ -f "$PROBE" ] && break; done
[ -f "$PROBE" ] && rm -f "$PROBE" && echo "PASS"
