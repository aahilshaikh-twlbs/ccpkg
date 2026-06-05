"""Interactive install wizard. Stdlib only, Python 3.9.

WizardState is a pure, I/O-free state machine (unit-tested directly). The
renderers (raw-mode termios + numbered fallback) are added separately and only
drive this state.
"""
import os
import select
import shutil
import sys
from typing import List, Optional, Set

from .selection import Stage

_SETTINGS_ID = "settings.json"
_SETTINGS_WARNING = ("warning: settings.json deselected — "
                     "Claude Code env will be incomplete")


class WizardState:
    def __init__(self, stages, preselected):
        # type: (List[Stage], Set[str]) -> None
        self.stages = stages
        self.selected = set(preselected)
        self.stage_index = 0
        self.cursor = 0
        self._done = False
        self._review = False

    # --- queries -------------------------------------------------------
    def current_stage(self):
        # type: () -> Stage
        return self.stages[self.stage_index]

    def is_selected(self, entry_id):
        # type: (str) -> bool
        return entry_id in self.selected

    def is_review(self):
        # type: () -> bool
        return self._review

    def is_done(self):
        # type: () -> bool
        return self._done

    def selected_ids(self):
        # type: () -> Set[str]
        return set(self.selected)

    # --- mutations -----------------------------------------------------
    def move(self, delta):
        # type: (int) -> None
        n = len(self.current_stage().entries)
        if n == 0:
            self.cursor = 0
            return
        self.cursor = max(0, min(n - 1, self.cursor + delta))

    def toggle(self):
        # type: () -> None
        entries = self.current_stage().entries
        if not entries:
            return
        eid = entries[self.cursor].id
        if eid in self.selected:
            self.selected.discard(eid)
        else:
            self.selected.add(eid)

    def select_all(self):
        # type: () -> None
        for e in self.current_stage().entries:
            self.selected.add(e.id)

    def select_none(self):
        # type: () -> None
        for e in self.current_stage().entries:
            self.selected.discard(e.id)

    def next_stage(self):
        # type: () -> None
        # Past the last stage we land on the REVIEW screen (not done); the user
        # confirms from there via confirm().
        if self.stage_index >= len(self.stages) - 1:
            self._review = True
            return
        self.stage_index += 1
        self.cursor = 0

    def confirm(self):
        # type: () -> None
        # Apply: Enter on the review screen finishes the wizard.
        self._done = True

    def prev_stage(self):
        # type: () -> None
        if self._review:
            self._review = False
            return
        if self._done:
            self._done = False
            return
        if self.stage_index > 0:
            self.stage_index -= 1
            self.cursor = 0


def _decode_key(seq):
    # type: (str) -> str
    mapping = {
        "\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
        "\r": "enter", "\n": "enter", " ": "space", "\x1b": "esc",
        "\x03": "ctrl-c",
    }
    if seq in mapping:
        return mapping[seq]
    return seq


# ANSI helpers
_CLEAR = "\x1b[2J\x1b[H"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"

# Glyphs (single display column each).
_DOT_DONE = "●"   # ● completed/current stage
_DOT_TODO = "○"   # ○ pending stage
_BOX_SEL = "◉"    # ◉ selected entry
_BOX_OFF = "○"    # ○ unselected entry
_POINTER = "▸"    # ▸ cursor


class _Palette:
    """SGR wrapper. When `on` is False every method is a no-op passthrough, so
    the same render code produces plain text for non-TTY/NO_COLOR output."""

    def __init__(self, enabled):
        # type: (bool) -> None
        self.on = bool(enabled)

    def _w(self, code, s):
        # type: (str, str) -> str
        return ("\x1b[%sm%s\x1b[0m" % (code, s)) if self.on else s

    def header(self, s):  # bold cyan
        return self._w("1;36", s)

    def accent(self, s):  # cyan
        return self._w("36", s)

    def cursor(self, s):  # bold cyan pointer
        return self._w("1;36", s)

    def dim(self, s):
        return self._w("2", s)

    def sel(self, s):     # green
        return self._w("32", s)

    def bold(self, s):
        return self._w("1", s)

    def warn(self, s):    # yellow
        return self._w("33", s)


def _color_enabled(out):
    # type: (object) -> bool
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(out.isatty())
    except Exception:
        return False


def _term_width(out):
    # type: (object) -> int
    try:
        cols = shutil.get_terminal_size((76, 24)).columns
    except Exception:
        cols = 76
    return max(54, min(cols, 84))


def _emit_top(out, title, crumb, width, pal):
    # type: (object, str, str, int, _Palette) -> None
    """Top rule: ┌─ <title> ──────── <crumb> ─┐ spanning `width` columns."""
    left = "┌─ " + title + " "
    right = " " + crumb + " ─┐"
    fill = max(1, width - len(left) - len(right))
    if pal.on:
        out.write("\x1b[36m┌─ \x1b[1m" + title + "\x1b[22m\x1b[36m "
                  + "─" * fill + " \x1b[1m" + crumb
                  + "\x1b[22m\x1b[36m ─┐\x1b[0m\r\n")
    else:
        out.write(left + "─" * fill + right + "\r\n")


def _emit_footer(out, left, right, width, pal):
    # type: (object, str, str, int, _Palette) -> None
    pad = max(2, width - len(left) - len(right) - 2)
    out.write(pal.dim("  " + left + " " * pad + right) + "\r\n")


def _stage_dots(state, pal):
    # type: (WizardState, _Palette) -> str
    return "".join(
        pal.accent(_DOT_DONE) if i <= state.stage_index else pal.dim(_DOT_TODO)
        for i in range(len(state.stages)))


def _render_numbered(state, out):
    # type: (WizardState, object) -> None
    stage = state.current_stage()
    out.write("\nStage %d/%d - %s\n"
              % (state.stage_index + 1, len(state.stages), stage.name))
    for i, e in enumerate(stage.entries, 1):
        mark = "x" if state.is_selected(e.id) else " "
        out.write("  %d. [%s] %-22s %s\n" % (i, mark, e.id, e.desc))
    out.write("Toggle # / 'a' all / 'n' none / Enter=continue: ")
    out.flush()


def _soft_warning(state):
    # type: (WizardState) -> Optional[str]
    """Non-blocking advisory shown on the review screen when settings.json is
    deselected. Returns None when there is nothing to warn about."""
    if _SETTINGS_ID not in state.selected:
        return _SETTINGS_WARNING
    return None


def _render_review_numbered(state, out):
    # type: (WizardState, object) -> None
    out.write("\nReview your selection:\n")
    for stage in state.stages:
        out.write("  %s:\n" % stage.name)
        chosen = [e for e in stage.entries if state.is_selected(e.id)]
        if chosen:
            for e in chosen:
                out.write("    [x] %s\n" % e.id)
        else:
            out.write("    (none)\n")
    warn = _soft_warning(state)
    if warn:
        out.write("  %s\n" % warn)
    out.write("Enter=apply / 'b'=back: ")
    out.flush()


def _render_review_raw(state, out):
    # type: (WizardState, object) -> None
    pal = _Palette(_color_enabled(out))
    width = _term_width(out)
    out.write(_CLEAR)
    _emit_top(out, "ccpkg install", "review selection", width, pal)
    out.write("\r\n")
    for stage in state.stages:
        out.write("  %s\r\n" % pal.bold(stage.name))
        chosen = [e for e in stage.entries if state.is_selected(e.id)]
        if chosen:
            for e in chosen:
                out.write("    %s %s\r\n" % (pal.sel(_BOX_SEL), e.id))
        else:
            out.write("    %s\r\n" % pal.dim("(none)"))
    warn = _soft_warning(state)
    if warn:
        out.write("\r\n  %s\r\n" % pal.warn(warn))
    out.write("\r\n")
    _emit_footer(out, "[ esc back ]", "[ ⏎ apply ]", width, pal)
    out.flush()


def _numbered_fallback(stages, preselected, in_stream, out_stream):
    # type: (List[Stage], Set[str], object, object) -> Set[str]
    state = WizardState(stages, preselected)
    while not state.is_done():
        if state.is_review():
            _render_review_numbered(state, out_stream)
            line = in_stream.readline()
            if line == "":                     # EOF -> apply as-is
                state.confirm()
                break
            if line.strip().lower() == "b":
                state.prev_stage()             # back to the last stage
            else:
                state.confirm()                # Enter (or anything) applies
            continue
        _render_numbered(state, out_stream)
        line = in_stream.readline()
        if line == "":                         # EOF -> accept rest as-is
            break
        cmd = line.strip().lower()
        if cmd == "":
            state.next_stage()
        elif cmd == "a":
            state.select_all()
        elif cmd == "n":
            state.select_none()
        elif cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(state.current_stage().entries):
                state.cursor = idx
                state.toggle()
        # unknown input: ignore, re-render
    return state.selected_ids()


def run_wizard(stages, preselected, in_stream=None, out_stream=None):
    # type: (List[Stage], Set[str], object, object) -> Set[str]
    """Collect a selection. Raw-mode TUI when both streams are a TTY; otherwise
    the numbered fallback."""
    in_stream = in_stream if in_stream is not None else sys.stdin
    out_stream = out_stream if out_stream is not None else sys.stdout
    if not stages:
        return set(preselected)
    if _is_tty(in_stream) and _is_tty(out_stream):
        # KeyboardInterrupt (BaseException) propagates for a clean Ctrl-C; any
        # other failure (e.g. missing termios) degrades to the numbered renderer.
        try:
            return _raw_mode_loop(stages, preselected, in_stream, out_stream)
        except Exception:
            return _numbered_fallback(stages, preselected, in_stream, out_stream)
    return _numbered_fallback(stages, preselected, in_stream, out_stream)


def _is_tty(stream):
    # type: (object) -> bool
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _render_raw(state, out):
    # type: (WizardState, object) -> None
    pal = _Palette(_color_enabled(out))
    width = _term_width(out)
    stage = state.current_stage()
    out.write(_CLEAR)
    _emit_top(out, "ccpkg install",
              "stage %d/%d · %s" % (state.stage_index + 1,
                                    len(state.stages), stage.name),
              width, pal)
    out.write("\r\n")
    hint = pal.dim("space toggle · ↑↓ move · ⏎ next · a all · n none · esc back")
    out.write("  %s   %s\r\n\r\n" % (_stage_dots(state, pal), hint))
    for i, e in enumerate(stage.entries):
        is_cur = (i == state.cursor)
        sel = state.is_selected(e.id)
        pointer = pal.cursor(_POINTER) if is_cur else " "
        box = pal.sel(_BOX_SEL) if sel else pal.dim(_BOX_OFF)
        name = "%-20s" % e.id
        name = pal.bold(name) if is_cur else name
        out.write(" %s %s %s %s\r\n" % (pointer, box, name, pal.dim(e.desc)))
    out.write("\r\n")
    _emit_footer(out, "[ esc back ]", "[ ⏎ continue → ]", width, pal)
    out.flush()


# Seconds to wait for a CSI tail before treating a bare ESC as the 'back' key.
# Small enough to be imperceptible, large enough that the [A/[B tail of an arrow
# key reliably arrives even when it lands a beat after the ESC byte.
_ESC_TAIL_TIMEOUT = 0.05


def _read_key(in_stream):
    # type: (object) -> str
    # Read raw bytes straight off the fd via os.read. Reading through a buffered
    # stream (e.g. sys.stdin) pulls the whole escape *burst* into Python's
    # userspace buffer on the first read and returns only the ESC byte — leaving
    # the "[A" tail invisible to select() on the fd, so every arrow decoded as a
    # lone ESC and fired 'back'. os.read takes exactly one byte from the kernel,
    # leaving the tail where select() can see it.
    fd = in_stream.fileno()
    first = os.read(fd, 1)
    if first == b"":
        return ""
    if first == b"\x1b":
        # Consume the CSI tail ONLY while bytes are actually pending, so a lone
        # Esc — a documented 'back' key — returns promptly instead of blocking.
        rest = b""
        while len(rest) < 2:
            r, _, _ = select.select([fd], [], [], _ESC_TAIL_TIMEOUT)
            if not r:
                break
            nxt = os.read(fd, 1)
            if nxt == b"":
                break
            rest += nxt
        return _decode_key((first + rest).decode("latin-1"))
    return _decode_key(first.decode("latin-1"))


def _raw_mode_loop(stages, preselected, in_stream, out_stream):
    # type: (List[Stage], Set[str], object, object) -> Set[str]
    import termios
    import tty
    state = WizardState(stages, preselected)
    fd = in_stream.fileno()
    old = termios.tcgetattr(fd)
    out_stream.write(_HIDE_CURSOR)
    try:
        tty.setraw(fd)
        while not state.is_done():
            if state.is_review():
                _render_review_raw(state, out_stream)
            else:
                _render_raw(state, out_stream)
            key = _read_key(in_stream)
            if key == "" or key == "ctrl-c":
                # EOF or Ctrl-C: abort. The finally below restores the terminal.
                raise KeyboardInterrupt
            if state.is_review():
                if key == "enter":
                    state.confirm()
                elif key in ("esc", "left"):
                    state.prev_stage()
                # ignore every other key on the review screen
                continue
            if key == "up":
                state.move(-1)
            elif key == "down":
                state.move(1)
            elif key == "space":
                state.toggle()
            elif key == "a":
                state.select_all()
            elif key == "n":
                state.select_none()
            elif key == "enter":
                state.next_stage()
            elif key in ("esc", "left"):
                state.prev_stage()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        out_stream.write(_SHOW_CURSOR)
        out_stream.flush()
    return state.selected_ids()
