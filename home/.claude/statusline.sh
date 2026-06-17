#!/usr/bin/env bash
# Claude Code status line script
# Reads JSON from stdin and outputs a formatted status line

input=$(cat)

RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
# Gruvbox-dark truecolor palette — matches the Claude Code custom theme (bright variants)
FG_MAGENTA='\033[38;2;211;134;155m'   # purple  #d3869b  (model name)
FG_GREEN='\033[38;2;184;187;38m'      # green   #b8bb26  (bar low / lines added)
FG_YELLOW='\033[38;2;250;189;47m'     # yellow  #fabd2f  (bar mid / cost)
FG_RED='\033[38;2;251;73;52m'         # red     #fb4934  (bar high / removed)
FG_CYAN='\033[38;2;142;192;124m'      # aqua    #8ec07c  (cache hit rate)
FG_WHITE='\033[38;2;235;219;178m'     # fg      #ebdbb2  (duration)
FG_BLUE='\033[38;2;131;165;152m'      # blue    #83a598  (git branch)
FG_GRAY='\033[38;2;146;131;116m'      # gray    #928374  (separators / labels)

model=$(echo "$input" | jq -r '.model.display_name // "Claude"')
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // 0')
ctx_size=$(echo "$input" | jq -r '.context_window.context_window_size // 0')
total_in=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0')
total_out=$(echo "$input" | jq -r '.context_window.total_output_tokens // 0')
cache_create=$(echo "$input" | jq -r '.context_window.current_usage.cache_creation_input_tokens // 0')
cache_read=$(echo "$input" | jq -r '.context_window.current_usage.cache_read_input_tokens // 0')
total_cost=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')
total_dur_ms=$(echo "$input" | jq -r '.cost.total_duration_ms // 0')
api_dur_ms=$(echo "$input" | jq -r '.cost.total_api_duration_ms // 0')
lines_added=$(echo "$input" | jq -r '.cost.total_lines_added // 0')
lines_removed=$(echo "$input" | jq -r '.cost.total_lines_removed // 0')
cwd=$(echo "$input" | jq -r '.cwd // ""')
session_id=$(echo "$input" | jq -r '.session_id // "default"')

# 1. MODEL
model_str=$(printf "${FG_MAGENTA}${BOLD}%s${RESET}" "$model")

# 1a. COMBINED COST BLOCK: sesh/dd/ww/mm/yy
day_cost_raw=$(~/.claude/daily-cost.sh   2>/dev/null)
week_cost_raw=$(~/.claude/weekly-cost.sh 2>/dev/null)
month_cost_raw=$(~/.claude/monthly-cost.sh 2>/dev/null)
year_cost_raw=$(~/.claude/yearly-cost.sh  2>/dev/null)

# 2. CONTEXT BAR
used_pct_int=${used_pct%.*}
used_pct_int=${used_pct_int:-0}
bar_filled=$(( used_pct_int / 10 ))
bar_filled=$(( bar_filled > 10 ? 10 : bar_filled ))
bar_empty=$(( 10 - bar_filled ))
bar_str=""
for (( i=0; i<bar_filled; i++ )); do bar_str+="█"; done
for (( i=0; i<bar_empty;  i++ )); do bar_str+="░"; done
if   (( used_pct_int >= 85 )); then bar_color="${FG_RED}"
elif (( used_pct_int >= 60 )); then bar_color="${FG_YELLOW}"
else                                 bar_color="${FG_GREEN}"
fi
if   (( ctx_size >= 1000000 )); then
    ctx_label=$(echo "$ctx_size" | awk '{printf "%gM", $1/1000000}')
elif (( ctx_size >= 1000 )); then
    ctx_label=$(echo "$ctx_size" | awk '{printf "%gK", $1/1000}')
else
    ctx_label="$ctx_size"
fi
ctx_str=$(printf "${bar_color}%s ${used_pct_int}%%${RESET}${FG_GRAY}/%s${RESET}" "$bar_str" "$ctx_label")

# 3. SESSION COST + COMBINED BLOCK
# Build parallel arrays of labels (gray) and amounts (yellow), then join with gray "/".
# Final output:  2026/May/session  $X.XX/$Y.YY/$Z.ZZ
cost_labels=()
cost_amounts=()

if [ "$total_cost" != "0" ] && [ "$total_cost" != "null" ] && [ -n "$total_cost" ]; then
    cost_labels+=("sesh")
    ge_tenth=$(echo "$total_cost >= 0.10" | bc 2>/dev/null)
    if [ "$ge_tenth" = "1" ]; then
        sess_fmt=$(printf "%.2f" "$total_cost" 2>/dev/null || echo "$total_cost")
        cost_amounts+=("\$${sess_fmt}")
    else
        cents=$(echo "$total_cost * 100" | bc 2>/dev/null | awk '{printf "%d", $1}')
        cost_amounts+=("${cents}¢")
    fi
fi

if [ -n "$day_cost_raw" ]; then
    cost_labels+=("dd")
    day_fmt=$(printf "%.2f" "$day_cost_raw" 2>/dev/null || echo "$day_cost_raw")
    cost_amounts+=("\$${day_fmt}")
fi

if [ -n "$week_cost_raw" ]; then
    cost_labels+=("ww")
    week_fmt=$(printf "%.2f" "$week_cost_raw" 2>/dev/null || echo "$week_cost_raw")
    cost_amounts+=("\$${week_fmt}")
fi

if [ -n "$month_cost_raw" ]; then
    cost_labels+=("mm")
    month_fmt=$(printf "%.2f" "$month_cost_raw" 2>/dev/null || echo "$month_cost_raw")
    cost_amounts+=("\$${month_fmt}")
fi

if [ -n "$year_cost_raw" ]; then
    cost_labels+=("yy")
    year_fmt=$(printf "%.2f" "$year_cost_raw" 2>/dev/null || echo "$year_cost_raw")
    cost_amounts+=("\$${year_fmt}")
fi

cost_str=""
if [ "${#cost_labels[@]}" -gt 0 ]; then
    gray_slash=$(printf "${FG_GRAY}/${RESET}")
    # Labels: all gray, slashes inherit color
    IFS=/ labels_joined="${cost_labels[*]}"
    labels_part=$(printf "${FG_GRAY}%s${RESET}" "$labels_joined")
    # Amounts: yellow numbers, gray slashes between
    amounts_part=""
    for amt in "${cost_amounts[@]}"; do
        if [ -z "$amounts_part" ]; then
            amounts_part=$(printf "${FG_YELLOW}%s${RESET}" "$amt")
        else
            amounts_part="${amounts_part}${gray_slash}$(printf "${FG_YELLOW}%s${RESET}" "$amt")"
        fi
    done
    cost_str="${labels_part}  ${amounts_part}"
fi

# 4. TOKEN COUNTS + CACHE HIT RATE
fmt_tokens() {
    local n=$1
    if   (( n >= 1000000 )); then echo "$(echo "$n" | awk '{printf "%.1fM", $1/1000000}')"
    elif (( n >= 1000 ));    then echo "$(echo "$n" | awk '{printf "%.0fK", $1/1000}')"
    else                          echo "$n"
    fi
}
in_fmt=$(fmt_tokens "$total_in")
out_fmt=$(fmt_tokens "$total_out")
cache_total=$(( total_in + cache_create + cache_read ))
if (( cache_total > 0 )) && (( cache_read > 0 )); then
    cache_pct=$(echo "$cache_read $cache_total" | awk '{printf "%d", ($1/$2)*100}')
    cache_suffix=$(printf " ${FG_CYAN}cache:%d%%${RESET}" "$cache_pct")
else
    cache_suffix=""
fi
tokens_str=$(printf "${FG_GRAY}in:%s out:%s%s${RESET}" "$in_fmt" "$out_fmt" "$cache_suffix")

# 5. LINES ADDED / REMOVED
lines_str=""
if (( lines_added > 0 )) || (( lines_removed > 0 )); then
    net=$(( lines_added - lines_removed ))
    if   (( net > 0 )); then net_str="+$net"; net_color="${FG_GREEN}"
    elif (( net < 0 )); then net_str="$net";  net_color="${FG_RED}"
    else                     net_str="0";     net_color="${FG_GRAY}"
    fi
    lines_str=$(printf "${FG_GREEN}+%d${RESET} ${FG_RED}-%d${RESET} ${DIM}${net_color}(%s)${RESET}" \
        "$lines_added" "$lines_removed" "$net_str")
fi

# 6. SESSION DURATION + API WAIT %
dur_str=""
if (( total_dur_ms > 0 )); then
    total_sec=$(( total_dur_ms / 1000 ))
    if   (( total_sec >= 3600 )); then
        h=$(( total_sec / 3600 )); m=$(( (total_sec % 3600) / 60 )); s=$(( total_sec % 60 ))
        dur_label=$(printf "%dh%dm%ds" "$h" "$m" "$s")
    elif (( total_sec >= 60 )); then
        m=$(( total_sec / 60 )); s=$(( total_sec % 60 ))
        dur_label=$(printf "%dm%ds" "$m" "$s")
    else
        dur_label="${total_sec}s"
    fi
    if (( api_dur_ms > 0 )) && (( total_dur_ms > 0 )); then
        api_pct=$(echo "$api_dur_ms $total_dur_ms" | awk '{printf "%d", ($1/$2)*100}')
        dur_str=$(printf "${FG_WHITE}%s${RESET} ${FG_GRAY}(api:%d%%)${RESET}" \
            "$dur_label" "$api_pct")
    else
        dur_str=$(printf "${FG_WHITE}%s${RESET}" "$dur_label")
    fi
fi

# 7. GIT BRANCH (+ dirty marker)
branch_str=""
if [ -n "$cwd" ] && [ -d "$cwd" ]; then
    branch=$(git -C "$cwd" --no-optional-locks symbolic-ref --short HEAD 2>/dev/null \
             || git -C "$cwd" --no-optional-locks rev-parse --short HEAD 2>/dev/null)
    if [ -n "$branch" ]; then
        if (( ${#branch} > 25 )); then
            branch="${branch:0:24}…"
        fi
        dirty=""
        if [ -n "$(git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null | head -n 1)" ]; then
            dirty=$(printf "${FG_YELLOW}*${RESET}")
        fi
        branch_str=$(printf "${FG_BLUE}%s${RESET}%s" "$branch" "$dirty")
    fi
fi

# 8. CLOCK (HH:MM, 24h)
clock_str=$(printf "${FG_GRAY}%s${RESET}" "$(date +%H:%M)")

# 0. NUKE MODE INDICATOR — gated on THIS session's actual effort (CLAUDE_EFFORT),
# NOT on settings.json. settings.json says what FUTURE sessions inherit; CLAUDE_EFFORT
# says what this running session actually is. Showing the indicator everywhere
# settings.json has ultracode would mislead in pre-arm sessions that aren't actually
# nuke'd. Indicator now appears only when this session was launched in xhigh effort.
nuke_str=""
if [ "${CLAUDE_EFFORT}" = "xhigh" ]; then
    nuke_str=$(printf "${BOLD}${FG_RED}🔴 NUKE${RESET} ${FG_GRAY}/nuke off when done${RESET}")
fi

# Assemble — single line, marquee handles overflow.
SEP=$(printf " ${FG_GRAY}|${RESET} ")
parts=()
[ -n "$nuke_str" ]   && parts+=("$nuke_str")
parts+=("$model_str")
parts+=("$ctx_str")
[ -n "$cost_str" ]   && parts+=("$cost_str")
parts+=("$tokens_str")
[ -n "$lines_str" ]  && parts+=("$lines_str")
[ -n "$dur_str" ]    && parts+=("$dur_str")
[ -n "$branch_str" ] && parts+=("$branch_str")
parts+=("$clock_str")

result=""
for part in "${parts[@]}"; do
    if [ -z "$result" ]; then
        result="$part"
    else
        result="${result}${SEP}${part}"
    fi
done

# Render the assembled line through the ANSI-aware marquee. If python or the
# helper is missing, fall back to printing the line as-is and let the terminal
# truncate — graceful degradation.
cols=$(tput cols 2>/dev/null)
[ -z "$cols" ] || (( cols <= 0 )) && cols=200

marquee="$HOME/.claude/statusline-marquee.py"
state_dir="${TMPDIR:-/tmp}"
safe_session=$(printf "%s" "$session_id" | tr -c 'A-Za-z0-9._-' '_')
state_file="${state_dir}/claude-statusline-scroll-${USER:-x}-${safe_session}.state"

if command -v python3 >/dev/null 2>&1 && [ -f "$marquee" ]; then
    printf "%b" "$result" | python3 "$marquee" --cols "$cols" --state "$state_file"
else
    printf "%b\n" "$result"
fi
