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
ostyle=$(echo "$input" | jq -r '.output_style.name // ""')

# "Fable 5 Lite" = an Opus base wearing the fable-5 output style.
case "$ostyle" in
  fable-5) model="Fable 5 Lite (1M)" ;;
esac
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // 0')
ctx_size=$(echo "$input" | jq -r '.context_window.context_window_size // 0')
total_in=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0')
total_out=$(echo "$input" | jq -r '.context_window.total_output_tokens // 0')
total_cost=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')
total_dur_ms=$(echo "$input" | jq -r '.cost.total_duration_ms // 0')
api_dur_ms=$(echo "$input" | jq -r '.cost.total_api_duration_ms // 0')
cwd=$(echo "$input" | jq -r '.cwd // ""')
session_id=$(echo "$input" | jq -r '.session_id // "default"')

# Per-session state dir, shared by the marquee scroll offset and the pet helper.
state_dir="${TMPDIR:-/tmp}"
safe_session=$(printf "%s" "$session_id" | tr -c 'A-Za-z0-9._-' '_')

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
    # Interleave each label with its amount so they read as pairs
    # (sesh $X · dd $Y · ww $Z · …), separated by a gray middot.
    cost_dot=$(printf "${FG_GRAY} · ${RESET}")
    for i in "${!cost_labels[@]}"; do
        pair=$(printf "${FG_GRAY}%s${RESET} ${FG_YELLOW}%s${RESET}" "${cost_labels[$i]}" "${cost_amounts[$i]}")
        if [ -z "$cost_str" ]; then
            cost_str="$pair"
        else
            cost_str="${cost_str}${cost_dot}${pair}"
        fi
    done
fi

# 4. SESSION DURATION + API WAIT %
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

# 7. PROJECT › BRANCH (+ dirty marker)
proj_branch_str=""
if [ -n "$cwd" ] && [ -d "$cwd" ]; then
    toplevel=$(git -C "$cwd" --no-optional-locks rev-parse --show-toplevel 2>/dev/null)
    if [ -n "$toplevel" ]; then project=$(basename "$toplevel"); else project=$(basename "$cwd"); fi
    branch=$(git -C "$cwd" --no-optional-locks symbolic-ref --short HEAD 2>/dev/null \
             || git -C "$cwd" --no-optional-locks rev-parse --short HEAD 2>/dev/null)
    (( ${#project} > 30 )) && project="${project:0:29}…"
    [ -n "$branch" ] && (( ${#branch} > 25 )) && branch="${branch:0:24}…"
    dirty=""
    if [ -n "$(git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null | head -n 1)" ]; then
        dirty=$(printf "${FG_YELLOW}*${RESET}")
    fi
    if [ -n "$branch" ]; then
        proj_branch_str=$(printf "${BOLD}${FG_WHITE}%s${RESET}${FG_GRAY} › ${RESET}${FG_BLUE}%s${RESET}%s" "$project" "$branch" "$dirty")
    elif [ -n "$project" ]; then
        proj_branch_str=$(printf "${BOLD}${FG_WHITE}%s${RESET}" "$project")
    fi
fi

# 8. BURN RATE + SESSION PET (stateful helper; fails silent to empty strings)
burn_str=""
pet_str=""
pet_helper="$HOME/.claude/statusline-pet.py"
if command -v python3 >/dev/null 2>&1 && [ -f "$pet_helper" ]; then
    pet_state="${state_dir}/claude-statusline-pet-${USER:-x}-${safe_session}.state"
    pet_tokens=$(( total_in + total_out ))
    { IFS= read -r burn_str; IFS= read -r pet_str; } < <(
        python3 "$pet_helper" --state "$pet_state" --tokens "$pet_tokens" \
            --ctx-pct "$used_pct_int" --dur-ms "$total_dur_ms" 2>/dev/null
    )
fi

# Assemble — single line, marquee handles overflow.
SEP=$(printf " ${FG_GRAY}|${RESET} ")
parts=()
parts+=("$model_str")
[ -n "$proj_branch_str" ] && parts+=("$proj_branch_str")
parts+=("$ctx_str")
[ -n "$dur_str" ]    && parts+=("$dur_str")
[ -n "$burn_str" ]   && parts+=("$burn_str")
[ -n "$cost_str" ]   && parts+=("$cost_str")
[ -n "$pet_str" ]    && parts+=("$pet_str")

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
state_file="${state_dir}/claude-statusline-scroll-${USER:-x}-${safe_session}.state"

if command -v python3 >/dev/null 2>&1 && [ -f "$marquee" ]; then
    printf "%b" "$result" | python3 "$marquee" --cols "$cols" --state "$state_file"
else
    printf "%b\n" "$result"
fi
