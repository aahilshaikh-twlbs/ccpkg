#!/usr/bin/env python3
"""ANSI-aware marquee renderer for the Claude Code statusline.

Reads a single styled line on stdin. If it fits within --cols visible chars,
prints as-is. Otherwise, advances a stored offset by (elapsed * speed) chars
and prints a --cols-wide window of the line, wrapping around through a small
gap ("   •   ") so the loop is visible.

State file format: "<offset_float>:<unix_timestamp_float>"
Falls through silently to "print as-is" on any error.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

SGR_RE = re.compile(r"\x1b\[[0-9;]*m")
RESET = "\x1b[0m"
GRAY = "\x1b[38;2;146;131;116m"
GAP_TEXT = "   •   "
GAP_VISIBLE_LEN = len(GAP_TEXT)


def visible_length(s: str) -> int:
    return len(SGR_RE.sub("", s))


def slice_styled(s: str, start: int, length: int) -> str:
    """Return a substring with `length` visible chars starting at visible index
    `start`. Replays all SGR codes seen before `start` so the window opens with
    the correct color/weight, and always closes with a reset."""
    if length <= 0:
        return ""
    out: list[str] = []
    active: list[str] = []
    vis = 0
    i = 0
    n = len(s)
    # Walk to the start, accumulating active SGR state.
    while i < n and vis < start:
        m = SGR_RE.match(s, i)
        if m:
            code = m.group(0)
            if code in ("\x1b[0m", "\x1b[m"):
                active = []
            else:
                active.append(code)
            i = m.end()
        else:
            i += 1
            vis += 1
    # Replay active styling so we open mid-stream in the right colors.
    if active:
        out.extend(active)
    emitted = 0
    while i < n and emitted < length:
        m = SGR_RE.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
        else:
            out.append(s[i])
            i += 1
            emitted += 1
    out.append(RESET)
    return "".join(out)


def load_state(path: str) -> tuple[float, float]:
    try:
        with open(path) as f:
            offset_str, ts_str = f.read().strip().split(":", 1)
            return float(offset_str), float(ts_str)
    except (OSError, ValueError):
        return 0.0, time.time()


def save_state(path: str, offset: float, ts: float) -> None:
    try:
        with open(path, "w") as f:
            f.write(f"{offset}:{ts}")
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cols", type=int, required=True)
    ap.add_argument("--state", required=True, help="path to scroll state file")
    ap.add_argument(
        "--speed",
        type=float,
        default=float(os.environ.get("CCPKG_STATUSLINE_SCROLL_SPEED", "2.0")),
        help="visible chars per second to advance the marquee",
    )
    args = ap.parse_args()

    line = sys.stdin.read()
    # Strip the single trailing newline if present, so visible_length is honest.
    if line.endswith("\n"):
        line = line[:-1]

    L = visible_length(line)
    cols = args.cols

    if cols <= 0:
        # Nothing to render into; bail.
        return 0

    force = os.environ.get("CCPKG_STATUSLINE_FORCE_SCROLL") == "1"
    # When forced, render through a virtual viewport narrower than the line so
    # the marquee always has something to scroll. CCPKG_STATUSLINE_VIEWPORT
    # overrides; otherwise default to ~70% of the actual line so the loop is
    # clearly visible. Cap at the real terminal width.
    if force:
        viewport_env = os.environ.get("CCPKG_STATUSLINE_VIEWPORT", "")
        try:
            target = int(viewport_env) if viewport_env else int(L * 0.7)
        except ValueError:
            target = int(L * 0.7)
        cols = max(20, min(cols, target))

    if L <= cols:
        # Fits — no scroll needed.
        sys.stdout.write(line + "\n")
        return 0

    gap_styled = f"{GRAY}{GAP_TEXT}{RESET}"
    full = line + gap_styled
    full_L = L + GAP_VISIBLE_LEN

    now = time.time()
    offset, last = load_state(args.state)
    elapsed = max(0.0, now - last)
    # Clamp huge gaps (e.g. machine slept) so we don't fast-forward weirdly.
    if elapsed > 10.0:
        elapsed = 0.0
    offset = (offset + elapsed * args.speed) % full_L
    save_state(args.state, offset, now)

    # Double the line so we can slice across the wrap point in one shot.
    doubled = full + full
    start = int(offset)
    sys.stdout.write(slice_styled(doubled, start, cols) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
