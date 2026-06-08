#!/usr/bin/env bash
# Smoke tests for the NUKE statusline indicator.
# Indicator is gated on THIS session's CLAUDE_EFFORT (set at launch), NOT on
# settings.json — settings.json defines what FUTURE sessions inherit; the
# indicator should reflect the running session's actual reality.
# Run: bash tests/test_statusline.sh
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")/.." && pwd)
STATUSLINE="$SCRIPT_DIR/home/.claude/statusline.sh"

JSON='{"model":{"display_name":"Opus"},"context_window":{"used_percentage":10,"context_window_size":200000,"total_input_tokens":1,"total_output_tokens":1,"current_usage":{"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"cost":{"total_cost_usd":0,"total_duration_ms":1000,"total_api_duration_ms":100,"total_lines_added":0,"total_lines_removed":0},"cwd":"/tmp"}'

fail=0

# Case 1: this session in xhigh + settings armed -> NUKE shown.
TMP=$(mktemp -d); mkdir -p "$TMP/.claude"
echo '{"ultracode": true}' > "$TMP/.claude/settings.json"
out=$(echo "$JSON" | CLAUDE_EFFORT=xhigh CLAUDE_CONFIG_DIR="$TMP/.claude" bash "$STATUSLINE")
if echo "$out" | grep -q "NUKE"; then
  echo "PASS xhigh+armed: NUKE indicator rendered"
else
  echo "FAIL xhigh+armed: NUKE indicator missing — got: $out"; fail=1
fi
rm -rf "$TMP"

# Case 2: this session in xhigh, settings DON'T have ultracode -> still show NUKE.
# (Session is genuinely in xhigh; statusline reflects session reality.)
TMP=$(mktemp -d); mkdir -p "$TMP/.claude"
echo '{}' > "$TMP/.claude/settings.json"
out=$(echo "$JSON" | CLAUDE_EFFORT=xhigh CLAUDE_CONFIG_DIR="$TMP/.claude" bash "$STATUSLINE")
if echo "$out" | grep -q "NUKE"; then
  echo "PASS xhigh+no-settings: NUKE indicator rendered (session is the truth)"
else
  echo "FAIL xhigh+no-settings: NUKE indicator missing — got: $out"; fail=1
fi
rm -rf "$TMP"

# Case 3 (the bug fix): settings armed but THIS session is high -> NO NUKE.
# Previously the indicator showed in pre-arm sessions; gating on CLAUDE_EFFORT fixes it.
TMP=$(mktemp -d); mkdir -p "$TMP/.claude"
echo '{"ultracode": true}' > "$TMP/.claude/settings.json"
out=$(echo "$JSON" | CLAUDE_EFFORT=high CLAUDE_CONFIG_DIR="$TMP/.claude" bash "$STATUSLINE")
if echo "$out" | grep -q "NUKE"; then
  echo "FAIL high+armed: NUKE indicator rendered in a non-xhigh session — got: $out"; fail=1
else
  echo "PASS high+armed: no NUKE (session not actually in nuke; settings is a future-state)"
fi
rm -rf "$TMP"

# Case 4: nothing armed, no xhigh -> no NUKE.
TMP=$(mktemp -d); mkdir -p "$TMP/.claude"
echo '{}' > "$TMP/.claude/settings.json"
out=$(echo "$JSON" | CLAUDE_EFFORT=high CLAUDE_CONFIG_DIR="$TMP/.claude" bash "$STATUSLINE")
if echo "$out" | grep -q "NUKE"; then
  echo "FAIL disarmed: NUKE rendered when it shouldn't"; fail=1
else
  echo "PASS disarmed: no NUKE indicator"
fi
rm -rf "$TMP"

# Case 5: no CLAUDE_EFFORT env at all (env-unset) -> no NUKE, no crash.
TMP=$(mktemp -d); mkdir -p "$TMP/.claude"
out=$(echo "$JSON" | env -u CLAUDE_EFFORT CLAUDE_CONFIG_DIR="$TMP/.claude" bash "$STATUSLINE")
if echo "$out" | grep -q "NUKE"; then
  echo "FAIL no-env: NUKE rendered with CLAUDE_EFFORT unset"; fail=1
else
  echo "PASS no-env: graceful, no NUKE"
fi
rm -rf "$TMP"

exit $fail
