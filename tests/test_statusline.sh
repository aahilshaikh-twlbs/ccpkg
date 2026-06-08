#!/usr/bin/env bash
# Minimal smoke tests for the NUKE statusline indicator.
# Run: bash tests/test_statusline.sh
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")/.." && pwd)
STATUSLINE="$SCRIPT_DIR/home/.claude/statusline.sh"

JSON='{"model":{"display_name":"Opus"},"context_window":{"used_percentage":10,"context_window_size":200000,"total_input_tokens":1,"total_output_tokens":1,"current_usage":{"cache_creation_input_tokens":0,"cache_read_input_tokens":0}},"cost":{"total_cost_usd":0,"total_duration_ms":1000,"total_api_duration_ms":100,"total_lines_added":0,"total_lines_removed":0},"cwd":"/tmp"}'

fail=0

# Case 1: armed -> NUKE present
TMP=$(mktemp -d); mkdir -p "$TMP/.claude"
echo '{"ultracode": true}' > "$TMP/.claude/settings.json"
out=$(echo "$JSON" | CLAUDE_CONFIG_DIR="$TMP/.claude" bash "$STATUSLINE")
if echo "$out" | grep -q "NUKE"; then
  echo "PASS armed: NUKE indicator rendered"
else
  echo "FAIL armed: NUKE indicator missing — got: $out"; fail=1
fi
rm -rf "$TMP"

# Case 2: disarmed -> NUKE absent
TMP=$(mktemp -d); mkdir -p "$TMP/.claude"
echo '{}' > "$TMP/.claude/settings.json"
out=$(echo "$JSON" | CLAUDE_CONFIG_DIR="$TMP/.claude" bash "$STATUSLINE")
if echo "$out" | grep -q "NUKE"; then
  echo "FAIL disarmed: NUKE indicator rendered when it shouldn't"; fail=1
else
  echo "PASS disarmed: no NUKE indicator"
fi
rm -rf "$TMP"

# Case 3: no settings.json at all -> still works (fail-open), no NUKE
TMP=$(mktemp -d); mkdir -p "$TMP/.claude"
out=$(echo "$JSON" | CLAUDE_CONFIG_DIR="$TMP/.claude" bash "$STATUSLINE")
if echo "$out" | grep -q "NUKE"; then
  echo "FAIL no-settings: NUKE indicator rendered when it shouldn't"; fail=1
else
  echo "PASS no-settings: graceful, no NUKE"
fi
rm -rf "$TMP"

exit $fail
