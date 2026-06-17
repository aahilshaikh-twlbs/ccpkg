#!/usr/bin/env bash
# Print this week's Claude cost (USD, plain number, no $ sign).
# Week starts on Monday. Stale-while-revalidate: 60s TTL, background refresh.
#
#   Cache format (single line): "YYYY-MM-DD:cost"   (key = Monday's date)
#   On read, if the stored Monday != this week's Monday, the cache is ignored.

set -u

CACHE="${TMPDIR:-/tmp}/claude-weekly-cost-${USER:-x}.cache"
LOCK="${CACHE}.lock"
TTL=60
LOCK_STALE=300
CCUSAGE_PIN="ccusage@18.0.11"

# Monday of the current week in YYYY-MM-DD form (BSD + GNU date compatible).
week_start() {
    local dow days_back secs
    dow=$(date +%u)            # 1=Mon ... 7=Sun
    days_back=$(( dow - 1 ))
    secs=$(( $(date +%s) - days_back * 86400 ))
    if date -r 0 >/dev/null 2>&1; then
        date -r "$secs" +%Y-%m-%d
    else
        date -d "@$secs" +%Y-%m-%d
    fi
}

# Same Monday as above but in YYYYMMDD form (ccusage --since).
week_start_compact() {
    local dow days_back secs
    dow=$(date +%u)
    days_back=$(( dow - 1 ))
    secs=$(( $(date +%s) - days_back * 86400 ))
    if date -r 0 >/dev/null 2>&1; then
        date -r "$secs" +%Y%m%d
    else
        date -d "@$secs" +%Y%m%d
    fi
}

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

    local key since total
    key=$(week_start)
    since=$(week_start_compact)
    total=$(npx -y "$CCUSAGE_PIN" daily --since "$since" --json 2>/dev/null \
        | jq -r '.totals.totalCost // empty' 2>/dev/null)

    [ -z "$total" ] && total="0"
    printf "%s:%s" "$key" "$total" > "$CACHE"
}

if [ "${1:-}" = "--refresh" ]; then
    refresh
    exit 0
fi

cached_value=""
need_refresh=1
if [ -f "$CACHE" ]; then
    line=$(cat "$CACHE" 2>/dev/null)
    cached_key="${line%%:*}"
    cached_cost="${line#*:}"
    if [ "$cached_key" = "$(week_start)" ] && [ -n "$cached_cost" ]; then
        cached_value="$cached_cost"
        age=$(( $(date +%s) - $(file_mtime "$CACHE") ))
        [ "$age" -lt "$TTL" ] && need_refresh=0
    fi
fi

if [ "$need_refresh" = "1" ]; then
    ( "$0" --refresh >/dev/null 2>&1 & ) >/dev/null 2>&1
fi

[ -n "$cached_value" ] && printf "%s" "$cached_value"
