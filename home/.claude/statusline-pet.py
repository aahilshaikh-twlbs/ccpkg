#!/usr/bin/env python3
"""Stateful session pet + live token burn-rate for the Claude Code statusline.

Keeps a small per-session state file (a ring of (timestamp, cumulative in+out
token) samples plus the pet's energy / last-activity / last-rate) and prints
TWO lines, both pre-colored with the gruvbox truecolor palette:

  line 1 — burn rate:  ⚡842K/h ▲      (live rolling rate, with a trend arrow)
  line 2 — the pet:    ʕ☆ᴥ☆ʔ⚡ Lv3 ▰▰▰▰▱ hyper

The pet EVOLVES through life stages as the session ages (egg→baby→kid→teen→
adult→elder) and its MOOD reacts to live signals: hyper while burning tokens,
sleepy when idle, stressed when the context window is nearly full, hungry/sick
when its energy bottoms out. Energy drains while idle and refills with activity.

Fails silently to two empty lines on any error so the statusline never breaks.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

# ── gruvbox-dark truecolor palette (matches statusline.sh) ──────────────────
R = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
GRN = "\x1b[38;2;184;187;38m"
YEL = "\x1b[38;2;250;189;47m"
RED = "\x1b[38;2;251;73;52m"
AQU = "\x1b[38;2;142;192;124m"
WHT = "\x1b[38;2;235;219;178m"
BLU = "\x1b[38;2;131;165;152m"
GRY = "\x1b[38;2;146;131;116m"
MAG = "\x1b[38;2;211;134;155m"

WINDOW = 180.0      # rolling burn-rate window (seconds)
MAXAGE = 300.0      # prune samples older than this
MAXSAMPLES = 240    # ring cap (~4 min at 1 sample/sec)
HYPER = 800_000     # tokens/hr above which the pet is "hyper"
IDLE_SLEEP = 120.0  # seconds without new tokens before the pet sleeps

# mood -> kaomoji eyes / trailing tag / sprite color
EYES = {
    "happy": "•ᴥ•", "hyper": "☆ᴥ☆", "sleepy": "-ᴥ-",
    "stressed": ";ᴥ;", "hungry": "•ᴥ•", "sick": "xᴥx",
}
TAG = {"hyper": "⚡", "sleepy": "z", "stressed": "!", "hungry": "…", "sick": "", "happy": ""}
MOOD_COLOR = {
    "happy": GRN, "hyper": YEL, "sleepy": GRY,
    "stressed": RED, "hungry": YEL, "sick": RED,
}


def fmt_rate(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(int(n))


def stage(minutes: float) -> tuple[int, str]:
    for limit, lvl, label in (
        (3, 0, "egg"), (10, 1, "baby"), (30, 2, "kid"),
        (60, 3, "teen"), (120, 4, "adult"),
    ):
        if minutes < limit:
            return lvl, label
    return 5, "elder"


def sprite(level: int, mood: str) -> str:
    eyes = EYES.get(mood, "•ᴥ•")
    tag = TAG.get(mood, "")
    if level == 0:
        body = "( ° )"                 # egg — pre-hatch, doesn't emote
    elif level == 5:
        body = f"ᕦʕ{eyes}ʔᕤ"          # elder — buff
    else:
        body = f"ʕ{eyes}ʔ"
    return body + tag


def load(path: str) -> dict:
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save(path: str, d: dict) -> None:
    try:
        with open(path, "w") as f:
            json.dump(d, f)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--tokens", type=int, default=0)   # cumulative in+out
    ap.add_argument("--ctx-pct", type=int, default=0)
    ap.add_argument("--dur-ms", type=int, default=0)    # session age
    a = ap.parse_args()

    now = time.time()
    st = load(a.state)
    samples = [s for s in st.get("samples", []) if isinstance(s, list) and len(s) == 2]
    energy = float(st.get("energy", 100.0))
    last_active = float(st.get("last_active", now))
    last_rate = float(st.get("last_rate", 0.0))

    # ── energy: drain while idle, refill with new tokens ────────────────────
    prev_ts, prev_tok = samples[-1] if samples else (now, a.tokens)
    dt = max(0.0, now - float(prev_ts))
    new_tok = max(0, a.tokens - int(prev_tok))
    energy = energy - 2.0 * (min(dt, 120.0) / 60.0) + new_tok / 400.0
    energy = max(0.0, min(100.0, energy))
    if new_tok > 0:
        last_active = now

    # ── sample ring ─────────────────────────────────────────────────────────
    samples.append([now, a.tokens])
    samples = [s for s in samples if now - float(s[0]) <= MAXAGE][-MAXSAMPLES:]

    # ── rolling burn rate (tokens/hr) ───────────────────────────────────────
    rate = 0.0
    computed = False
    window = [s for s in samples if now - float(s[0]) <= WINDOW]
    if len(window) >= 2:
        t0, k0 = float(window[0][0]), int(window[0][1])
        span = now - t0
        if span >= 3.0:
            rate = max(0.0, (a.tokens - k0) / span * 3600.0)
            computed = True
    if not computed and a.dur_ms > 3000:        # warm-up: session average
        rate = a.tokens / (a.dur_ms / 3_600_000.0)

    # ── trend (hysteresis to avoid flicker) ─────────────────────────────────
    if rate > last_rate * 1.15 and rate - last_rate > 5000:
        trend = "up"
    elif rate < last_rate * 0.85 and last_rate - rate > 5000:
        trend = "down"
    else:
        trend = "flat"

    # ── mood (priority order) ───────────────────────────────────────────────
    idle = now - last_active
    if a.ctx_pct >= 85:
        mood = "stressed"
    elif rate >= HYPER:
        mood = "hyper"
    elif energy < 8:
        mood = "sick"
    elif energy < 20:
        mood = "hungry"
    elif idle >= IDLE_SLEEP and rate < 50_000:
        mood = "sleepy"
    else:
        mood = "happy"

    level, _label = stage(a.dur_ms / 60_000.0)

    save(a.state, {
        "samples": samples, "energy": energy,
        "last_active": last_active, "last_rate": rate,
    })

    # ── render: burn rate ────────────────────────────────────────────────────
    if rate > 0:
        arrow = {"up": "▲", "down": "▼", "flat": "▬"}[trend]
        acolor = {"up": RED, "down": GRN, "flat": GRY}[trend]
        burn = f"{GRY}⚡{R}{YEL}{fmt_rate(rate)}/h{R} {acolor}{arrow}{R}"
    else:
        burn = f"{GRY}⚡idle{R}"

    # ── render: pet ──────────────────────────────────────────────────────────
    sc = MOOD_COLOR.get(mood, GRN)
    filled = max(0, min(5, int(round(energy / 20.0))))
    barc = GRN if energy >= 60 else (YEL if energy >= 30 else RED)
    bar = f"{barc}{'▰' * filled}{GRY}{'▱' * (5 - filled)}{R}"
    pet = (f"{sc}{sprite(level, mood)}{R} {GRY}Lv{level}{R} "
           f"{bar} {DIM}{sc}{mood}{R}")

    sys.stdout.write(burn + "\n" + pet + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write("\n\n")   # never break the statusline
        sys.exit(0)
