#!/usr/bin/env bash
# Print today's Claude cost (USD, plain number, no $ sign).
# Stale-while-revalidate: 60s TTL, background refresh, never blocks the statusline.
#
#   Cache format (single line): "YYYY-MM-DD:cost"   e.g. "2026-06-16:12.34"
#   On read, if the stored date != current date, the cache is ignored.

set -u

CACHE="${TMPDIR:-/tmp}/claude-daily-cost-${USER:-x}.cache"
LOCK="${CACHE}.lock"
TTL=60
LOCK_STALE=300
CCUSAGE_PIN="ccusage@18.0.11"

current_day() { date +%Y-%m-%d; }

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

    local day since total
    day=$(current_day)
    since=$(date +%Y%m%d)
    total=$(npx -y "$CCUSAGE_PIN" daily --since "$since" --json 2>/dev/null \
        | jq -r '.totals.totalCost // empty' 2>/dev/null)

    [ -z "$total" ] && total="0"
    printf "%s:%s" "$day" "$total" > "$CACHE"
}

if [ "${1:-}" = "--refresh" ]; then
    refresh
    exit 0
fi

cached_value=""
need_refresh=1
if [ -f "$CACHE" ]; then
    line=$(cat "$CACHE" 2>/dev/null)
    cached_day="${line%%:*}"
    cached_cost="${line#*:}"
    if [ "$cached_day" = "$(current_day)" ] && [ -n "$cached_cost" ]; then
        cached_value="$cached_cost"
        age=$(( $(date +%s) - $(file_mtime "$CACHE") ))
        [ "$age" -lt "$TTL" ] && need_refresh=0
    fi
fi

if [ "$need_refresh" = "1" ]; then
    ( "$0" --refresh >/dev/null 2>&1 & ) >/dev/null 2>&1
fi

[ -n "$cached_value" ] && printf "%s" "$cached_value"
