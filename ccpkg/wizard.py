"""Interactive install wizard. Stdlib only, Python 3.9.

WizardState is a pure, I/O-free state machine (unit-tested directly). The
renderers (raw-mode termios + numbered fallback) are added separately and only
drive this state.
"""
import os
import random
import select
import shutil
import sys
import textwrap
from typing import List, Optional, Set

from .selection import Stage

_SETTINGS_ID = "settings.json"
_SETTINGS_WARNING = ("warning: settings.json deselected — "
                     "Claude Code env will be incomplete")


class WizardState:
    # Install presets, in display order. "Custom" walks the per-group picker;
    # the others compute a selection set from the stages and jump to review.
    PRESETS = ["Everything", "Recommended", "Minimal", "Custom"]

    def __init__(self, stages, preselected, existing=False):
        # type: (List[Stage], Set[str], bool) -> None
        self.stages = stages
        self.selected = set(preselected)
        self.stage_index = 0
        self.cursor = 0
        self._done = False
        self._review = False
        self._intro = True
        # Preset-select screen, shown after the intro and before the groups.
        self._preset = False
        self.preset_cursor = self.PRESETS.index("Recommended")
        # True when a saved profile already exists (re-run / update), so the
        # splash can say "existing install" instead of "fresh install".
        self.existing = bool(existing)

    # --- queries -------------------------------------------------------
    def current_stage(self):
        # type: () -> Stage
        return self.stages[self.stage_index]

    def is_selected(self, entry_id):
        # type: (str) -> bool
        return entry_id in self.selected

    def is_intro(self):
        # type: () -> bool
        return self._intro

    def is_preset(self):
        # type: () -> bool
        return self._preset

    def all_entries(self):
        # type: () -> List
        return [e for stage in self.stages for e in stage.entries]

    def preset_ids(self, name):
        # type: (str) -> Set[str]
        """The id-set a named preset would select, computed from the stages.

        Everything = all; Recommended = default-on entries; Minimal = required
        entries (falling back to Recommended when nothing is flagged required);
        Custom = the current preselection (left untouched, picked by hand)."""
        entries = self.all_entries()
        if name == "Everything":
            return {e.id for e in entries}
        if name == "Recommended":
            return {e.id for e in entries if e.default}
        if name == "Minimal":
            required = {e.id for e in entries if getattr(e, "required", False)}
            return required if required else {e.id for e in entries if e.default}
        return set(self.selected)  # Custom

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
    def begin(self):
        # type: () -> None
        # Leave the intro/preset screens and land on the first group stage.
        self._intro = False
        self._preset = False

    def to_preset(self):
        # type: () -> None
        # Leave the intro splash and land on the preset-select screen.
        self._intro = False
        self._preset = True

    def preset_move(self, delta):
        # type: (int) -> None
        n = len(self.PRESETS)
        self.preset_cursor = max(0, min(n - 1, self.preset_cursor + delta))

    def apply_preset(self):
        # type: () -> None
        # Enter on the preset screen: "Custom" walks the groups; any other
        # preset fixes the selection and jumps straight to the review screen.
        name = self.PRESETS[self.preset_cursor]
        if name == "Custom":
            self.begin()
            return
        self.selected = self.preset_ids(name)
        self._preset = False
        self._review = True

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
        if self._preset:
            # Back from the preset screen returns to the intro splash.
            self._preset = False
            self._intro = True
            return
        if self._review:
            self._review = False
            return
        if self._done:
            self._done = False
            return
        if self.stage_index > 0:
            self.stage_index -= 1
            self.cursor = 0
        else:
            # Back from the first stage returns to the intro splash.
            self._intro = True


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

# Glyphs.
_DOT_DONE = "●"      # ● completed/current group
_DOT_TODO = "○"      # ○ pending group
_CHECK_ON = "[✓]"    # selected entry — brackets read as 'toggleable'
_CHECK_OFF = "[ ]"   # unselected entry
_POINTER = "▸"       # ▸ cursor
_BAR = "▌"           # ▌ group-header accent bar

# Block wordmark for the splash. "ANSI Shadow" style — the letters c c p k g
# in shadowed box-drawing glyphs. Six rows, all 41 columns wide.
_WORDMARK_ART = [
    " ██████╗ ██████╗██████╗ ██╗  ██╗ ██████╗ ",
    "██╔════╝██╔════╝██╔══██╗██║ ██╔╝██╔════╝ ",
    "██║     ██║     ██████╔╝█████╔╝ ██║  ███╗",
    "██║     ██║     ██╔═══╝ ██╔═██╗ ██║   ██║",
    "╚██████╗╚██████╗██║     ██║  ██╗╚██████╔╝",
    " ╚═════╝ ╚═════╝╚═╝     ╚═╝  ╚═╝ ╚═════╝ ",
]


# Curated accent hues, à la Claude Code's /color. A per-run scheme picks one of
# these; header/cursor/accent all derive from it, while 'sel' (green) and 'warn'
# (yellow) stay fixed so their *meaning* (selected / warning) is stable.
_ACCENT_CODES = [
    "36",        # cyan (the original)
    "35",        # magenta
    "34",        # blue
    "32",        # green
    "96",        # bright cyan
    "95",        # bright magenta
    "94",        # bright blue
    "38;5;39",   # azure
    "38;5;170",  # orchid
    "38;5;208",  # orange
    "38;5;75",   # sky blue
    "38;5;141",  # violet
]
_DEFAULT_ACCENT = "36"
# Module-level active accent for the current run. Reset per run by
# _init_color_scheme(); seedable so tests can assert a stable scheme.
_active_accent = _DEFAULT_ACCENT


def _init_color_scheme(seed=None):
    # type: (Optional[int]) -> str
    """Choose this run's accent hue at random. Pass a seed for a deterministic
    scheme (tests). Affects color output only; plain mode is unchanged."""
    global _active_accent
    _active_accent = random.Random(seed).choice(_ACCENT_CODES)
    return _active_accent


class _Palette:
    """SGR wrapper. When `on` is False every method is a no-op passthrough, so
    the same render code produces plain text for non-TTY/NO_COLOR output. The
    accent hue is per-run (see _init_color_scheme); meaning-bearing colors
    (sel=green, warn=yellow) are fixed regardless of the accent."""

    def __init__(self, enabled, accent=_DEFAULT_ACCENT):
        # type: (bool, str) -> None
        self.on = bool(enabled)
        self.accent_code = accent

    def _w(self, code, s):
        # type: (str, str) -> str
        return ("\x1b[%sm%s\x1b[0m" % (code, s)) if self.on else s

    def header(self, s):  # bold accent
        return self._w("1;" + self.accent_code, s)

    def accent(self, s):  # accent
        return self._w(self.accent_code, s)

    def cursor(self, s):  # bold accent pointer
        return self._w("1;" + self.accent_code, s)

    def dim(self, s):
        return self._w("2", s)

    def sel(self, s):     # green
        return self._w("32", s)

    def selbold(self, s):  # bold green
        return self._w("1;32", s)

    def bold(self, s):
        return self._w("1", s)

    def warn(self, s):    # yellow
        return self._w("33", s)

    def bad(self, s):     # red
        return self._w("31", s)


def _make_palette(out):
    # type: (object) -> _Palette
    """The palette for a render: color gated on _color_enabled(out), accent set
    to this run's scheme."""
    return _Palette(_color_enabled(out), _active_accent)


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


def _left_margin(width):
    # type: (int) -> str
    """Spaces to left-pad every line so the `width`-column box sits centered in
    the terminal. Falls back to no margin when the size can't be determined."""
    try:
        cols = shutil.get_terminal_size((76, 24)).columns
    except Exception:
        cols = width
    return " " * max(0, (cols - width) // 2)


# Below these the framed wizard can't render without overflow/scroll, so we show
# a "terminal too small" guard instead (like a TUI's resize gate). Width is fixed
# (the hint line + frame need ~80 cols); height is per-screen — one row per option
# plus fixed chrome — so the tallest group drives it.
_MIN_COLS = 80
_GROUP_CHROME_ROWS = 10   # fixed lines around the list + detail (top/header/hint/footer + blanks)
_OTHER_SCREEN_ROWS = 14   # intro / preset / review all fit within this


def _terminal_dims():
    # type: () -> Tuple[int, int]
    """(columns, lines) of the controlling terminal, with an 80x24 fallback."""
    try:
        ts = shutil.get_terminal_size((80, 24))
        return ts.columns, ts.lines
    except Exception:
        return 80, 24


def _required_dims(state):
    # type: (WizardState) -> Tuple[int, int]
    """(cols, rows) the current screen needs to render without overflow/scroll.
    The option screen needs one row per entry plus fixed chrome (+1 so the top
    bar stays put); the intro/preset/review screens are short and fixed."""
    on_group = not (state.is_intro() or state.is_preset() or state.is_review())
    if not on_group:
        return _MIN_COLS, _OTHER_SCREEN_ROWS
    entries = state.current_stage().entries
    detail_rows = 1
    if entries:
        cur = entries[state.cursor]
        meta = _entry_meta(cur)
        detail = cur.desc + ((" · " + meta) if meta else "")
        detail_rows = max(1, len(textwrap.wrap(detail, max(8, _MIN_COLS - 4))))
    # fixed chrome + one row per option + the wrapped detail lines + 1 (keep the
    # top bar from scrolling off).
    rows = _GROUP_CHROME_ROWS + len(entries) + detail_rows + 1
    return _MIN_COLS, rows


def _render_too_small(out, cur_w, cur_h, need_w, need_h, pal=None):
    # type: (object, int, int, int, int, object) -> None
    """A centered 'terminal too small' guard. The deficient dimension is shown in
    red and the satisfied one in green, with the target dims below, so the user
    knows exactly how far to drag the window."""
    if pal is None:
        pal = _make_palette(out)
    cols = cur_w if cur_w > 0 else need_w
    w_col = pal.sel if cur_w >= need_w else pal.bad
    h_col = pal.sel if cur_h >= need_h else pal.bad

    def line(plain, colored):
        pad = " " * max(0, (cols - len(plain)) // 2)
        out.write(pad + colored + "\r\n")

    out.write(_CLEAR)
    out.write("\r\n" * max(0, cur_h // 2 - 3))
    line("Terminal size too small:", pal.bold("Terminal size too small:"))
    line("  Width = %d Height = %d" % (cur_w, cur_h),
         "  " + pal.bold("Width = ") + w_col(str(cur_w)) + " "
         + pal.bold("Height = ") + h_col(str(cur_h)))
    out.write("\r\n")
    line("Needed for current config:", pal.bold("Needed for current config:"))
    line("  Width = %d Height = %d" % (need_w, need_h),
         "  " + pal.bold("Width = %d Height = %d" % (need_w, need_h)))
    out.flush()


def _entry_meta(e):
    # type: (object) -> str
    """One-line metadata for an entry's detail line. Files show `path · mode`;
    plugins show `plugin · scope`; the mboard shows `coordinator`;
    packs show `skill pack` or `agent pack` based on group."""
    kind = getattr(e, "kind", "")
    if kind == "file":
        parts = [p for p in (getattr(e, "path", ""), getattr(e, "mode", "")) if p]
        return " · ".join(parts)
    if kind == "plugin":
        scope = getattr(e, "scope", "")
        return "plugin" + ((" · " + scope) if scope else "")
    if kind == "mboard":
        return "coordinator"
    if kind == "pack":
        group = getattr(e, "group", "")
        if group == "Skills":
            return "skill pack"
        if group == "Agents":
            return "agent pack"
        return "pack"
    return ""


def _name_col_width(entries, gutter=4):
    # type: (List, int) -> int
    """Width of the entry-name column = widest id + a comfortable gutter, so
    descriptions align in one clean column instead of crowding the longest id.
    A fixed %-20s overflowed on ids like 'settings.local.json.tmpl' (24 chars)."""
    if not entries:
        return gutter
    return max(len(e.id) for e in entries) + gutter


def _clip(s, max_cols):
    # type: (str, int) -> str
    """Truncate s to at most max_cols display columns, marking elision with '…'.
    Descriptions/metadata are plain text (one char == one column here), so a
    slice is accurate. Returns '' when there is no room at all. Keeps row content
    inside the framed width so it never spills past the top-bar's right corner."""
    if max_cols <= 0:
        return ""
    if len(s) <= max_cols:
        return s
    if max_cols == 1:
        return "…"
    return s[:max_cols - 1] + "…"


def _emit_top(out, title, crumb, width, pal, margin=""):
    # type: (object, str, str, int, _Palette, str) -> None
    """Top rule: ┌─ <title> ──────── <crumb> ─┐ spanning `width` columns,
    shifted right by `margin` to center the box."""
    left = "┌─ " + title + " "
    right = " " + crumb + " ─┐"
    fill = max(1, width - len(left) - len(right))
    if pal.on:
        ac = pal.accent_code
        out.write(margin + "\x1b[%sm┌─ \x1b[1m%s\x1b[22m\x1b[%sm %s \x1b[1m%s"
                  "\x1b[22m\x1b[%sm ─┐\x1b[0m\r\n"
                  % (ac, title, ac, "─" * fill, crumb, ac))
    else:
        out.write(margin + left + "─" * fill + right + "\r\n")


def _emit_footer(out, left, right, width, pal, margin=""):
    # type: (object, str, str, int, _Palette, str) -> None
    pad = max(2, width - len(left) - len(right) - 2)
    out.write(margin + pal.dim("  " + left + " " * pad + right) + "\r\n")


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
    col = _name_col_width(stage.entries)
    for i, e in enumerate(stage.entries, 1):
        mark = "x" if state.is_selected(e.id) else " "
        out.write("  %d. [%s] %-*s %s\n" % (i, mark, col, e.id, e.desc))
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
    pal = _make_palette(out)
    width = _term_width(out)
    m = _left_margin(width)
    out.write(_CLEAR)
    _emit_top(out, "ccpkg install", "review selection", width, pal, m)
    out.write(m + "\r\n")
    for stage in state.stages:
        out.write(m + "  %s\r\n" % pal.bold(stage.name))
        chosen = [e for e in stage.entries if state.is_selected(e.id)]
        if chosen:
            for e in chosen:
                out.write(m + "    %s %s\r\n" % (pal.selbold(_CHECK_ON), e.id))
        else:
            out.write(m + "    %s\r\n" % pal.dim("(none)"))
    warn = _soft_warning(state)
    if warn:
        out.write(m + "\r\n")
        out.write(m + "  %s\r\n" % pal.warn(warn))
    out.write(m + "\r\n")
    _emit_footer(out, "[ esc back ]", "[ ⏎ apply ]", width, pal, m)
    out.flush()


def _render_intro_numbered(state, out):
    # type: (WizardState, object) -> None
    n = len(state.stages)
    out.write("\nccpkg — Claude Code environment-as-code\n")
    out.write("%d stage%s to configure.\n" % (n, "" if n == 1 else "s"))
    out.flush()


def _numbered_fallback(stages, preselected, in_stream, out_stream,
                       existing=False):
    # type: (List[Stage], Set[str], object, object, bool) -> Set[str]
    state = WizardState(stages, preselected, existing=existing)
    # The intro is display-only in the headless renderer (no extra input): show
    # the banner once, then drop straight into the first stage.
    if state.is_intro():
        _render_intro_numbered(state, out_stream)
        state.begin()
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


def run_wizard(stages, preselected, in_stream=None, out_stream=None,
               existing=False):
    # type: (List[Stage], Set[str], object, object, bool) -> Set[str]
    """Collect a selection. Raw-mode TUI when both streams are a TTY; otherwise
    the numbered fallback. `existing` marks a re-run (a saved profile exists)."""
    in_stream = in_stream if in_stream is not None else sys.stdin
    out_stream = out_stream if out_stream is not None else sys.stdout
    if not stages:
        return set(preselected)
    # Pick this run's randomized accent scheme (no-op for plain output).
    _init_color_scheme()
    if _is_tty(in_stream) and _is_tty(out_stream):
        # KeyboardInterrupt (BaseException) propagates for a clean Ctrl-C; any
        # other failure (e.g. missing termios) degrades to the numbered renderer.
        try:
            return _raw_mode_loop(stages, preselected, in_stream, out_stream,
                                  existing=existing)
        except Exception:
            return _numbered_fallback(stages, preselected, in_stream, out_stream,
                                      existing=existing)
    return _numbered_fallback(stages, preselected, in_stream, out_stream,
                              existing=existing)


def _is_tty(stream):
    # type: (object) -> bool
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _render_intro_raw(state, out):
    # type: (WizardState, object) -> None
    """Splash shown once before the first group: block wordmark, tagline,
    install status, a one-line orientation, and a begin/cancel footer."""
    pal = _make_palette(out)
    width = _term_width(out)
    m = _left_margin(width)
    out.write(_CLEAR)
    _emit_top(out, "ccpkg", "welcome", width, pal, m)
    out.write(m + "\r\n")
    for row in _WORDMARK_ART:
        out.write(m + "   %s\r\n" % pal.accent(row))
    out.write(m + "\r\n")
    out.write(m + "   %s\r\n" % pal.dim("Claude Code environment-as-code"))
    n = len(state.stages)
    status = "existing install · %d group%s" if state.existing else \
             "fresh install · %d group%s"
    out.write(m + "   %s\r\n" % pal.dim(status % (n, "" if n == 1 else "s")))
    out.write(m + "\r\n")
    orient = "↑↓ move · space toggles · ⏎ continues · esc back"
    out.write(m + "   %s\r\n" % pal.dim(orient))
    out.write(m + "\r\n")
    _emit_footer(out, "[ ⏎ begin ]", "[ esc cancel ]", width, pal, m)
    out.flush()


# Preset blurbs, in WizardState.PRESETS order.
_PRESET_BLURBS = {
    "Everything": "every group and option",
    "Recommended": "the sensible default set",
    "Minimal": "only the essentials",
    "Custom": "pick group by group",
}


def _render_preset_raw(state, out):
    # type: (WizardState, object) -> None
    """Preset-select screen, shown after the intro and before the per-group
    picker. ↑↓ move · ⏎ select · ← back · esc cancel."""
    pal = _make_palette(out)
    width = _term_width(out)
    m = _left_margin(width)
    out.write(_CLEAR)
    _emit_top(out, "ccpkg install", "choose a preset", width, pal, m)
    out.write(m + "\r\n")
    out.write(m + "  %s %s\r\n" % (pal.accent(_BAR), pal.header("Install preset")))
    out.write(m + "\r\n")
    hint = pal.dim("↑↓ move · ⏎ select · ← back · esc cancel")
    out.write(m + "  %s\r\n" % hint)
    out.write(m + "\r\n")
    col = max(len(n) for n in state.PRESETS) + 4
    for i, name in enumerate(state.PRESETS):
        is_cur = (i == state.preset_cursor)
        pointer = pal.cursor(_POINTER) if is_cur else " "
        label = "%-*s" % (col, name)
        label = pal.bold(label) if is_cur else label
        blurb = _PRESET_BLURBS.get(name, "")
        if name == "Custom":
            tail = blurb
        else:
            count = len(state.preset_ids(name))
            tail = "%s · %d item%s" % (blurb, count, "" if count == 1 else "s")
        out.write(m + " %s %s %s\r\n" % (pointer, label, pal.dim(tail)))
    out.write(m + "\r\n")
    _emit_footer(out, "[ esc cancel ]", "[ ⏎ select ]", width, pal, m)
    out.flush()


def render_summary(summary, out):
    # type: (dict, object) -> None
    """Non-interactive post-install recap, boxed in the wizard's style. Writes
    to `out` and returns — there is no input loop. `summary` is a dict with:

      applied: list of (label, status) tuples
      plugins: dict name -> status
      mboard: dict name -> status
      notes:   list of str
      skipped: list of label

    All keys optional; missing ones render as an empty/(none) section."""
    pal = _make_palette(out)
    width = _term_width(out)
    m = _left_margin(width)
    _emit_top(out, "ccpkg install", "complete", width, pal, m)
    out.write(m + "\r\n")

    def _checked_section(title, rows):
        out.write(m + "  %s\r\n" % pal.bold(title))
        if rows:
            for label, status in rows:
                if status:
                    out.write(m + "    %s %s  %s\r\n"
                              % (pal.selbold(_CHECK_ON), label, pal.dim(status)))
                else:
                    out.write(m + "    %s %s\r\n" % (pal.selbold(_CHECK_ON), label))
        else:
            out.write(m + "    %s\r\n" % pal.dim("(none)"))
        out.write(m + "\r\n")

    applied = summary.get("applied") or []
    _checked_section("Applied", [(str(a), str(b)) for a, b in applied])

    plugins = summary.get("plugins") or {}
    _checked_section("Plugins", [(str(k), str(v)) for k, v in plugins.items()])

    mboard = summary.get("mboard") or {}
    _checked_section("Mboard", [(str(k), str(v)) for k, v in mboard.items()])

    packs = summary.get("packs") or {}
    if packs:
        _checked_section("Packs", [(str(k), str(v)) for k, v in packs.items()])

    skipped = summary.get("skipped") or []
    if skipped:
        out.write(m + "  %s\r\n" % pal.bold("Skipped"))
        for label in skipped:
            out.write(m + "    %s %s\r\n"
                      % (pal.dim(_CHECK_OFF), pal.dim(str(label))))
        out.write(m + "\r\n")

    notes = summary.get("notes") or []
    if notes:
        out.write(m + "  %s\r\n" % pal.bold("Notes"))
        for note in notes:
            out.write(m + "    %s %s\r\n" % (pal.dim("·"), pal.dim(str(note))))
        out.write(m + "\r\n")

    _emit_footer(out, "[ done ]", "[ ccpkg ]", width, pal, m)
    out.flush()


def _render_raw(state, out):
    # type: (WizardState, object) -> None
    pal = _make_palette(out)
    width = _term_width(out)
    m = _left_margin(width)
    stage = state.current_stage()
    out.write(_CLEAR)
    _emit_top(out, "ccpkg install",
              "group %d/%d" % (state.stage_index + 1, len(state.stages)),
              width, pal, m)
    out.write(m + "\r\n")
    # Prominent group header — an accent bar + the group name in bold, so each
    # section is clearly its own grouping rather than a flat list.
    n_sel = sum(1 for e in stage.entries if state.is_selected(e.id))
    n_all = len(stage.entries)
    out.write(m + "  %s %s   %s\r\n" % (
        pal.accent(_BAR), pal.header(stage.name),
        pal.dim("%d option%s · %d selected"
                % (n_all, "" if n_all == 1 else "s", n_sel))))
    out.write(m + "  %s\r\n" % _stage_dots(state, pal))
    out.write(m + "\r\n")
    hint = pal.dim("space toggle · ↑↓ move · ⏎ next · ← → groups · a all · n none · esc back")
    out.write(m + "  %s\r\n" % hint)
    out.write(m + "\r\n")
    col = _name_col_width(stage.entries)
    # The fixed prefix left of the description is " " + pointer + " " + "[ ]" +
    # " " + name + " " == col + 8 visible columns; clip each description to what
    # remains inside the `width`-column frame so it never overruns the top bar.
    desc_w = width - col - 8
    for i, e in enumerate(stage.entries):
        is_cur = (i == state.cursor)
        sel = state.is_selected(e.id)
        pointer = pal.cursor(_POINTER) if is_cur else " "
        box = pal.selbold(_CHECK_ON) if sel else pal.dim(_CHECK_OFF)
        name = "%-*s" % (col, e.id)
        name = pal.bold(name) if is_cur else name
        out.write(m + " %s %s %s %s\r\n"
                  % (pointer, box, name, pal.dim(_clip(e.desc, desc_w))))
    # Detail line for the highlighted entry: its description plus metadata
    # (path · mode for files, plugin · scope for plugins) so the cursor's
    # purpose and what it contributes are obvious at a glance.
    if stage.entries:
        cur = stage.entries[state.cursor]
        meta = _entry_meta(cur)
        detail = cur.desc + ((" · " + meta) if meta else "")
        # List rows are clipped for scannability; show the FULL highlighted
        # description here, word-wrapped within the frame — this is the "read
        # more". Prefix is 4 visible cols ("  " + pointer + " "); continuation
        # lines indent 4 to align under the text.
        wrapped = textwrap.wrap(detail, max(8, width - 4)) or [""]
        out.write(m + "\r\n")
        out.write(m + "  %s %s\r\n" % (pal.accent(_POINTER), pal.dim(wrapped[0])))
        for cont in wrapped[1:]:
            out.write(m + "    %s\r\n" % pal.dim(cont))
    out.write(m + "\r\n")
    _emit_footer(out, "[ esc back ]", "[ ⏎ continue → ]", width, pal, m)
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


def _raw_mode_loop(stages, preselected, in_stream, out_stream, existing=False):
    # type: (List[Stage], Set[str], object, object, bool) -> Set[str]
    import termios
    import tty
    state = WizardState(stages, preselected, existing=existing)
    fd = in_stream.fileno()
    old = termios.tcgetattr(fd)
    out_stream.write(_HIDE_CURSOR)
    try:
        tty.setraw(fd)
        while not state.is_done():
            need_w, need_h = _required_dims(state)
            cur_w, cur_h = _terminal_dims()
            if cur_w < need_w or cur_h < need_h:
                _render_too_small(out_stream, cur_w, cur_h, need_w, need_h)
                # Poll so the guard clears within ~250ms of a resize, while still
                # letting Esc / q / Ctrl-C / EOF abort.
                r, _, _ = select.select([fd], [], [], 0.25)
                if r:
                    key = _read_key(in_stream)
                    if key in ("", "ctrl-c", "esc", "q"):
                        raise KeyboardInterrupt
                continue
            if state.is_intro():
                _render_intro_raw(state, out_stream)
            elif state.is_preset():
                _render_preset_raw(state, out_stream)
            elif state.is_review():
                _render_review_raw(state, out_stream)
            else:
                _render_raw(state, out_stream)
            key = _read_key(in_stream)
            if key == "" or key == "ctrl-c":
                # EOF or Ctrl-C: abort. The finally below restores the terminal.
                raise KeyboardInterrupt
            if state.is_intro():
                if key in ("enter", "right"):
                    state.to_preset()
                elif key in ("esc", "q"):
                    # Only Esc/q cancels on the splash (terminal restored below).
                    # Arrow keys must NOT cancel — left/right just navigate.
                    raise KeyboardInterrupt
                # ignore every other key (incl. lone 'left') on the intro
                continue
            if state.is_preset():
                if key == "up":
                    state.preset_move(-1)
                elif key == "down":
                    state.preset_move(1)
                elif key in ("enter", "right"):
                    state.apply_preset()
                elif key == "left":
                    # Left navigates back to the intro (not a cancel).
                    state.prev_stage()
                elif key in ("esc", "q"):
                    # Only Esc/q cancels; arrows never do.
                    raise KeyboardInterrupt
                # ignore every other key on the preset screen
                continue
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
            elif key in ("enter", "right"):
                state.next_stage()
            elif key in ("esc", "left"):
                state.prev_stage()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        out_stream.write(_SHOW_CURSOR)
        out_stream.flush()
    return state.selected_ids()
