#!/usr/bin/env bash
# Print the current calendar year's Claude cost (USD, plain number, no $ sign).
# Stale-while-revalidate: 60s TTL, background refresh, never blocks the statusline.
#
#   Cache format (single line): "YYYY:cost"      e.g. "2026:720.70"
#   On read, if the stored year != current year, the cache is ignored.
#   On --refresh, the cache is rewritten unconditionally.

set -u

CACHE="${TMPDIR:-/tmp}/claude-yearly-cost-${USER:-x}.cache"
LOCK="${CACHE}.lock"
TTL=60
LOCK_STALE=300
CCUSAGE_PIN="ccusage@18.0.11"

current_year() { date +%Y; }

# Portable mtime: BSD (macOS) stat -f %m, GNU (Linux) stat -c %Y.
file_mtime() {
    if stat -f %m "$1" >/dev/null 2>&1; then
        stat -f %m "$1"
    else
        stat -c %Y "$1"
    fi
}

refresh() {
    if [ -e "$LOCK" ]; then
        local lock_age=$(( $(date +%s) - $(file_mtime "$LOCK") ))
        if [ "$lock_age" -lt "$LOCK_STALE" ]; then
            return 0
        fi
        rm -f "$LOCK"
    fi
    : > "$LOCK"
    trap 'rm -f "$LOCK"' EXIT

    local year since total
    year=$(current_year)
    since="${year}0101"
    total=$(npx -y "$CCUSAGE_PIN" monthly --since "$since" --json 2>/dev/null \
        | jq -r '.totals.totalCost // empty' 2>/dev/null)

    [ -z "$total" ] && total="0"
    printf "%s:%s" "$year" "$total" > "$CACHE"
}

if [ "${1:-}" = "--refresh" ]; then
    refresh
    exit 0
fi

cached_value=""
need_refresh=1
if [ -f "$CACHE" ]; then
    line=$(cat "$CACHE" 2>/dev/null)
    cached_year="${line%%:*}"
    cached_cost="${line#*:}"
    if [ "$cached_year" = "$(current_year)" ] && [ -n "$cached_cost" ]; then
        cached_value="$cached_cost"
        age=$(( $(date +%s) - $(file_mtime "$CACHE") ))
        [ "$age" -lt "$TTL" ] && need_refresh=0
    fi
fi

if [ "$need_refresh" = "1" ]; then
    ( "$0" --refresh >/dev/null 2>&1 & ) >/dev/null 2>&1
fi

[ -n "$cached_value" ] && printf "%s" "$cached_value"
