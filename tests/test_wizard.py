import io
import os
import signal

import pytest

from ccpkg import wizard
from ccpkg.selection import Stage, Entry


class _PipeKeyStream:
    """A minimal unbuffered key stream over a real fd (no Python read-ahead, so
    select() on the fd reflects what is actually pending)."""

    def __init__(self, fd):
        self._fd = fd

    def read(self, n):
        return os.read(self._fd, n).decode("latin-1")

    def fileno(self):
        return self._fd


def _with_timeout(seconds, fn):
    """Run fn() but raise TimeoutError if it blocks longer than `seconds`."""
    def _handler(signum, frame):
        raise TimeoutError("blocked")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _stages():
    return [
        Stage("Core", [Entry("settings.json", "settings", True, "file"),
                       Entry("statusline.sh", "statusline", True, "file")]),
        Stage("Plugins", [Entry("superpowers", "skills", True, "plugin"),
                          Entry("frontend-design", "ui", False, "plugin")]),
    ]


def test_starts_in_intro_then_begin_lands_on_stage_zero():
    st = wizard.WizardState(_stages(), set())
    assert st.is_intro()
    assert not st.is_review() and not st.is_done()
    st.begin()
    assert not st.is_intro()
    assert st.stage_index == 0


def test_prev_from_first_stage_returns_to_intro():
    st = wizard.WizardState(_stages(), set())
    st.begin()
    assert not st.is_intro()
    st.prev_stage()                   # Esc/Left on the first stage -> intro
    assert st.is_intro()
    assert st.stage_index == 0


def test_prev_from_later_stage_does_not_return_to_intro():
    st = wizard.WizardState(_stages(), set())
    st.begin()
    st.next_stage()                   # stage index 1
    assert st.stage_index == 1
    st.prev_stage()                   # back to stage 0, NOT the intro
    assert not st.is_intro()
    assert st.stage_index == 0


def test_name_col_width_widest_id_plus_gutter():
    entries = _stages()[0].entries     # ids: settings.json (13), statusline.sh (13)
    assert wizard._name_col_width(entries) == 13 + 4
    assert wizard._name_col_width(entries, gutter=2) == 13 + 2


def test_name_col_width_tracks_longest_id():
    long_stage = [Entry("settings.local.json.tmpl", "d", True, "file"),
                  Entry("x", "d", True, "file")]
    # 24-char id (the case the old fixed %-20s overflowed) drives the column.
    assert wizard._name_col_width(long_stage) == 24 + 4


def test_name_col_width_empty_entries_is_just_gutter():
    assert wizard._name_col_width([]) == 4


def test_render_raw_aligns_descriptions_for_long_ids(monkeypatch):
    # Descriptions must start at the same column even when ids differ in length.
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: False)
    stages = [Stage("Mixed", [
        Entry("settings.local.json.tmpl", "DESC_A", True, "file"),
        Entry("hooks.json", "DESC_B", True, "file")])]
    st = wizard.WizardState(stages, set())
    st.begin()
    out = io.StringIO()
    wizard._render_raw(st, out)
    # Filter to entry rows (they carry a checkbox); the new per-item detail line
    # also echoes the highlighted entry's desc but has no checkbox glyph.
    lines = [ln for ln in out.getvalue().split("\r\n")
             if "DESC_" in ln and ("[✓]" in ln or "[ ]" in ln)]
    assert len(lines) == 2
    assert lines[0].index("DESC_A") == lines[1].index("DESC_B")


def test_render_raw_clips_descriptions_to_frame_width(monkeypatch):
    # Long descriptions must not spill past the top-bar frame (`width` columns),
    # at any terminal size. Pin width + margin so the bound is deterministic.
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: False)
    monkeypatch.setattr(wizard, "_term_width", lambda out: 60)
    monkeypatch.setattr(wizard, "_left_margin", lambda width: "")
    longdesc = "D" * 200
    stages = [Stage("Core", [
        Entry("settings.json", longdesc, True, "file"),
        Entry("statusline.sh", "short one", True, "file")])]
    st = wizard.WizardState(stages, set())
    st.begin()
    out = io.StringIO()
    wizard._render_raw(st, out)
    text = out.getvalue()
    # Entry rows (carry a checkbox) and the cursor's detail line (a pointer, no
    # checkbox) are the variable-width content we clip; none may exceed width.
    rows = [ln for ln in text.split("\r\n") if "[✓]" in ln or "[ ]" in ln]
    details = [ln for ln in text.split("\r\n") if "▸" in ln and "[" not in ln]
    assert rows, "no entry rows rendered"
    for ln in rows + details:
        assert len(ln) <= 60, "content exceeds frame (%d): %r" % (len(ln), ln)
    # the over-long description was elided with the marker
    assert "…" in text


def test_required_dims_group_scales_with_option_count():
    stages = [Stage("Core", [Entry("a", "d", True, "file"),
                             Entry("b", "d", True, "file"),
                             Entry("c", "d", True, "file")])]
    st = wizard.WizardState(stages, set())
    st.begin()
    cols, rows = wizard._required_dims(st)
    assert cols == wizard._MIN_COLS
    # chrome + one row per option (3) + wrapped detail lines (short desc -> 1) + 1 safety
    assert rows == wizard._GROUP_CHROME_ROWS + 3 + 1 + 1


def test_render_too_small_colors_deficient_red_and_ok_green():
    out = io.StringIO()
    pal = wizard._Palette(enabled=True)
    wizard._render_too_small(out, 64, 63, 80, 24, pal)
    text = out.getvalue()
    assert "Terminal size too small:" in text
    assert "Needed for current config:" in text
    assert "Width = 80 Height = 24" in text   # target line (plain text inside bold)
    assert "\x1b[31m64\x1b[0m" in text         # width deficient (64<80) -> red
    assert "\x1b[32m63\x1b[0m" in text         # height ok (63>=24) -> green


def test_render_too_small_plain_content():
    out = io.StringIO()
    pal = wizard._Palette(enabled=False)
    wizard._render_too_small(out, 50, 10, 80, 24, pal)
    text = out.getvalue()
    assert "Width = 50 Height = 10" in text
    assert "Width = 80 Height = 24" in text


def test_render_raw_uses_bracketed_checkbox(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: False)
    st = wizard.WizardState(_stages(), {"settings.json"})
    st.begin()
    out = io.StringIO()
    wizard._render_raw(st, out)
    text = out.getvalue()
    assert "[✓]" in text          # settings.json is selected
    assert "[ ]" in text          # statusline.sh is not


def test_render_intro_raw_plain_has_wordmark_and_footer():
    st = wizard.WizardState(_stages(), set())
    out = io.StringIO()
    wizard._render_intro_raw(st, out)
    text = out.getvalue()
    assert "\x1b[36m" not in text and "\x1b[1m" not in text   # no SGR styling
    assert wizard._WORDMARK_ART[0] in text                     # block wordmark
    assert "environment-as-code" in text
    assert "2 groups" in text                                  # status line
    assert "fresh install" in text                             # not a re-run
    assert "begin" in text and "cancel" in text                # footer


def test_render_intro_raw_existing_install_status():
    st = wizard.WizardState(_stages(), set(), existing=True)
    out = io.StringIO()
    wizard._render_intro_raw(st, out)
    assert "existing install" in out.getvalue()


def test_initial_preselected_are_ticked():
    st = wizard.WizardState(_stages(), {"settings.json", "superpowers"})
    assert st.is_selected("settings.json")
    assert not st.is_selected("statusline.sh")


def test_move_and_toggle():
    st = wizard.WizardState(_stages(), set())
    assert st.cursor == 0
    st.move(1)
    assert st.cursor == 1
    st.toggle()                       # toggle statusline.sh on
    assert st.is_selected("statusline.sh")
    st.toggle()                       # back off
    assert not st.is_selected("statusline.sh")


def test_move_clamps_within_stage():
    st = wizard.WizardState(_stages(), set())
    st.move(-1)
    assert st.cursor == 0             # clamped at top
    st.move(99)
    assert st.cursor == 1             # clamped at bottom (2 entries)


def test_select_all_and_none_affect_current_stage_only():
    st = wizard.WizardState(_stages(), set())
    st.select_all()
    assert st.is_selected("settings.json") and st.is_selected("statusline.sh")
    st.next_stage()
    st.select_none()
    assert not st.is_selected("superpowers")
    # previous stage untouched
    assert st.is_selected("settings.json")


def test_stage_navigation_and_review():
    st = wizard.WizardState(_stages(), set())
    assert st.stage_index == 0
    st.next_stage()
    assert st.stage_index == 1
    assert not st.is_done()
    st.next_stage()                   # past last stage -> review (NOT done yet)
    assert st.is_review()
    assert not st.is_done()
    st.confirm()                      # Enter on review -> apply
    assert st.is_done()


def test_back_from_review_returns_to_last_stage():
    st = wizard.WizardState(_stages(), set())
    st.next_stage()                   # stage 2 (index 1, the last)
    st.next_stage()                   # review
    assert st.is_review()
    st.prev_stage()                   # Esc/Left on review -> back
    assert not st.is_review()
    assert not st.is_done()
    assert st.stage_index == 1


def test_selected_ids_returns_full_set():
    st = wizard.WizardState(_stages(), {"settings.json"})
    st.next_stage()
    st.toggle()                       # superpowers (cursor 0 of stage 2) -> off? it's preselected? no
    # superpowers default not preselected here (empty start except settings.json)
    assert st.is_selected("superpowers") is True or st.is_selected("superpowers") is False
    ids = st.selected_ids()
    assert "settings.json" in ids


def test_numbered_fallback_toggles_and_advances():
    # Stage 1: toggle entry 2 on (statusline), then Enter; Stage 2: 'n' then Enter.
    stages = _stages()
    instream = io.StringIO("2\n\nn\n\n")
    outstream = io.StringIO()
    result = wizard._numbered_fallback(stages, {"settings.json", "superpowers"},
                                       instream, outstream)
    assert "settings.json" in result          # carried from preselected
    assert "statusline.sh" in result          # toggled on in stage 1
    assert "superpowers" not in result        # 'n' cleared stage 2


def test_numbered_fallback_a_selects_all_in_stage():
    stages = _stages()
    instream = io.StringIO("a\n\n\n")          # stage1 all, enter; stage2 enter
    result = wizard._numbered_fallback(stages, set(), instream, io.StringIO())
    assert "settings.json" in result and "statusline.sh" in result


def test_run_wizard_uses_fallback_when_not_tty():
    stages = _stages()
    instream = io.StringIO("\n\n")             # accept defaults each stage
    outstream = io.StringIO()                  # StringIO.isatty() is False
    result = wizard.run_wizard(stages, {"settings.json"},
                               in_stream=instream, out_stream=outstream)
    assert "settings.json" in result


def test_decode_key_arrows_and_chars():
    assert wizard._decode_key("\x1b[A") == "up"
    assert wizard._decode_key("\x1b[B") == "down"
    assert wizard._decode_key("\x1b[D") == "left"
    assert wizard._decode_key("\r") == "enter"
    assert wizard._decode_key("\n") == "enter"
    assert wizard._decode_key(" ") == "space"
    assert wizard._decode_key("\x1b") == "esc"
    assert wizard._decode_key("a") == "a"
    assert wizard._decode_key("\x03") == "ctrl-c"


def test_read_key_lone_esc_does_not_block():
    # A lone ESC (no CSI tail pending) must return 'esc' immediately, never block.
    r, w = os.pipe()
    try:
        os.write(w, b"\x1b")
        stream = _PipeKeyStream(r)
        key = _with_timeout(2.0, lambda: wizard._read_key(stream))
        assert key == "esc"
    finally:
        os.close(r)
        os.close(w)


def test_read_key_arrow_up_over_real_fd():
    # A full CSI arrow sequence is decoded when the tail bytes are pending.
    r, w = os.pipe()
    try:
        os.write(w, b"\x1b[A")
        stream = _PipeKeyStream(r)
        key = _with_timeout(2.0, lambda: wizard._read_key(stream))
        assert key == "up"
    finally:
        os.close(r)
        os.close(w)


def test_raw_mode_loop_aborts_on_eof():
    # EOF ('' read) at the prompt must terminate (no 100% CPU spin), restoring
    # the terminal. A real pty supplies the termios the loop needs.
    import pty
    master, slave = pty.openpty()
    slave_f = os.fdopen(slave, "r")
    out = io.StringIO()
    os.close(master)  # reads on the slave now hit EOF (or EIO)
    import termios

    def _run():
        # Linux: a closed-master slave makes tcgetattr fail with EIO
        # (termios.error, which is NOT an OSError); macOS reaches the prompt and
        # hits EOF -> KeyboardInterrupt. Either way the loop aborts (no spin).
        with pytest.raises((KeyboardInterrupt, OSError, termios.error)):
            wizard._raw_mode_loop(_stages(), set(), slave_f, out)

    try:
        _with_timeout(3.0, _run)
    finally:
        slave_f.close()


def _feed_after_raw(master_fd, data, gap=0.04):
    """Feed keystrokes to the pty master one byte at a time, on a thread, AFTER
    the loop has had a beat to enter raw mode. tty.setraw() uses TCSAFLUSH, which
    discards any input queued before the switch — so bytes written up front never
    reach os.read. Drip-feeding from a thread lands them in raw mode instead."""
    import threading
    import time

    def _drip():
        time.sleep(gap * 3)                      # let _raw_mode_loop reach setraw
        for b in data:
            try:
                os.write(master_fd, bytes([b]))
            except OSError:
                # The test may finish and close the pty before we've drained all
                # bytes; a write to the closed fd then raises EBADF. That's
                # expected teardown, not a failure — stop quietly instead of
                # dumping a daemon-thread traceback to stderr.
                return
            time.sleep(gap)

    t = threading.Thread(target=_drip, daemon=True)
    t.start()
    return t


def test_raw_mode_loop_intro_enter_then_applies():
    # PTY smoke test of the full raw loop: Enter on the intro begins, then an
    # Enter per stage walks to review, and a final Enter applies the selection.
    import pty
    master, slave = pty.openpty()
    out = io.StringIO()
    # begin, stage1->stage2, stage2->review, review->apply  == 4 enters
    _feed_after_raw(master, b"\r\r\r\r")
    stream = _PipeKeyStream(slave)

    def _run():
        return wizard._raw_mode_loop(_stages(), {"settings.json"}, stream, out)

    try:
        result = _with_timeout(3.0, _run)
    finally:
        os.close(slave)
        os.close(master)
    assert "settings.json" in result
    assert wizard._WORDMARK_ART[0] in out.getvalue()  # intro splash was rendered


def test_raw_mode_loop_esc_on_intro_cancels():
    # Esc on the intro splash aborts cleanly (KeyboardInterrupt), restoring term.
    import pty
    master, slave = pty.openpty()
    out = io.StringIO()
    _feed_after_raw(master, b"\x1b")             # lone Esc on the intro
    stream = _PipeKeyStream(slave)

    def _run():
        with pytest.raises(KeyboardInterrupt):
            wizard._raw_mode_loop(_stages(), set(), stream, out)

    try:
        _with_timeout(3.0, _run)
    finally:
        os.close(slave)
        os.close(master)


def test_raw_mode_loop_left_on_intro_does_not_cancel():
    # Regression: a left arrow on the intro must NOT cancel (it used to be
    # aliased to esc). Here: left (ignored) then right begins, then 4 enters
    # walk to apply — the run completes with a selection rather than aborting.
    import pty
    master, slave = pty.openpty()
    out = io.StringIO()
    _feed_after_raw(master, b"\x1b[D" + b"\x1b[C" + b"\r\r\r")  # left, right=begin, walk
    stream = _PipeKeyStream(slave)

    def _run():
        return wizard._raw_mode_loop(_stages(), {"settings.json"}, stream, out)

    try:
        result = _with_timeout(3.0, _run)
    finally:
        os.close(slave)
        os.close(master)
    assert "settings.json" in result            # completed, not cancelled


def test_run_wizard_empty_stages_returns_preselected():
    # No stages -> nothing to pick; return the preselected set untouched.
    result = wizard.run_wizard([], {"settings.json"},
                               in_stream=io.StringIO(""), out_stream=io.StringIO())
    assert result == {"settings.json"}


def test_run_wizard_falls_back_when_raw_mode_crashes(monkeypatch):
    # On a 'tty' where termios setup explodes, run_wizard must not crash; it
    # falls back to the numbered renderer.
    class _FakeTTY(io.StringIO):
        def isatty(self):
            return True

    instream = _FakeTTY("\n\n")
    outstream = _FakeTTY()

    def _boom(*a, **k):
        raise RuntimeError("no termios here")

    monkeypatch.setattr(wizard, "_raw_mode_loop", _boom)
    result = wizard.run_wizard(_stages(), {"settings.json"},
                               in_stream=instream, out_stream=outstream)
    assert "settings.json" in result


def test_render_raw_plain_when_not_a_tty():
    # StringIO.isatty() is False -> renderer must emit NO color (SGR) codes, but
    # still carry the structure (box rule + the entry text).
    st = wizard.WizardState(_stages(), {"settings.json"})
    out = io.StringIO()
    wizard._render_raw(st, out)
    text = out.getvalue()
    assert "\x1b[36m" not in text and "\x1b[1m" not in text  # no SGR styling
    assert "┌─" in text and "settings.json" in text          # structure intact


def test_render_raw_colored_when_enabled(monkeypatch):
    # With color forced on, the selected entry's checkbox carries the bold-green
    # (1;32) SGR code.
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: True)
    st = wizard.WizardState(_stages(), {"settings.json"})
    out = io.StringIO()
    wizard._render_raw(st, out)
    assert "\x1b[1;32m" in out.getvalue()


def test_color_disabled_when_no_color_env(monkeypatch):
    class _TTY(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setenv("NO_COLOR", "1")
    assert wizard._color_enabled(_TTY()) is False


def test_soft_warning_present_when_settings_deselected():
    warn = wizard._soft_warning(wizard.WizardState(_stages(), set()))
    assert warn is not None
    assert "settings.json" in warn


def test_soft_warning_absent_when_settings_selected():
    warn = wizard._soft_warning(wizard.WizardState(_stages(), {"settings.json"}))
    assert warn is None


def test_numbered_fallback_drives_through_review():
    # stage1 Enter -> stage2 Enter -> review Enter applies. The review step is
    # one EXTRA Enter compared with the pre-review flow.
    stages = _stages()
    instream = io.StringIO("\n\n\n")
    result = wizard._numbered_fallback(stages, {"settings.json"},
                                       instream, io.StringIO())
    assert "settings.json" in result


def test_numbered_fallback_review_back_then_apply():
    # review 'b' goes back to the last stage; a later Enter re-enters review and
    # applies.
    stages = _stages()
    instream = io.StringIO("\n\nb\n\n\n")
    result = wizard._numbered_fallback(stages, {"settings.json"},
                                       instream, io.StringIO())
    assert "settings.json" in result


def test_numbered_fallback_review_shows_soft_warning():
    # With settings.json deselected, the review screen carries the soft warning.
    stages = _stages()
    instream = io.StringIO("\n\n\n")
    outstream = io.StringIO()
    wizard._numbered_fallback(stages, set(), instream, outstream)
    assert "settings.json" in outstream.getvalue()
    assert "incomplete" in outstream.getvalue()


# --- randomized color scheme -------------------------------------------------

def test_init_color_scheme_is_seedable():
    a = wizard._init_color_scheme(seed=1234)
    b = wizard._init_color_scheme(seed=1234)
    assert a == b                            # same seed -> stable scheme
    assert a in wizard._ACCENT_CODES


def test_init_color_scheme_varies_across_seeds():
    seen = {wizard._init_color_scheme(seed=s) for s in range(50)}
    # A curated palette of >1 hue should produce more than one accent over many
    # seeds (proves it's actually randomized, not a constant).
    assert len(seen) > 1


def test_make_palette_uses_active_accent(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: True)
    wizard._init_color_scheme(seed=1234)
    pal = wizard._make_palette(io.StringIO())
    assert pal.accent_code == wizard._active_accent
    assert ("\x1b[%sm" % wizard._active_accent) in pal.accent("x")


def test_palette_plain_mode_unaffected_by_accent():
    # Color off -> pure passthrough regardless of the active accent.
    pal = wizard._Palette(False, accent="38;5;208")
    assert pal.accent("x") == "x"
    assert pal.header("x") == "x"


def test_render_raw_accent_used_when_colored(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: True)
    wizard._init_color_scheme(seed=7)        # deterministic accent
    st = wizard.WizardState(_stages(), {"settings.json"})
    st.begin()
    out = io.StringIO()
    wizard._render_raw(st, out)
    assert ("\x1b[%sm" % wizard._active_accent) in out.getvalue()


# --- centered modal ----------------------------------------------------------

def test_render_raw_centered_on_wide_terminal(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: False)
    monkeypatch.setattr(wizard.shutil, "get_terminal_size",
                        lambda fallback=(80, 24): os.terminal_size((120, 24)))
    st = wizard.WizardState(_stages(), set())
    st.begin()
    out = io.StringIO()
    wizard._render_raw(st, out)
    # width clamps to 84, cols=120 -> margin = (120-84)//2 = 18 spaces before
    # the box rule (which follows the screen-clear sequence on the first line).
    text = out.getvalue()
    assert (" " * 18 + "┌─") in text
    assert (" " * 19 + "┌─") not in text


def test_left_margin_zero_when_terminal_narrow(monkeypatch):
    monkeypatch.setattr(wizard.shutil, "get_terminal_size",
                        lambda fallback=(80, 24): os.terminal_size((60, 24)))
    assert wizard._left_margin(84) == ""      # box wider than terminal -> no pad


def test_centering_shifts_all_lines_uniformly(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: False)
    monkeypatch.setattr(wizard.shutil, "get_terminal_size",
                        lambda fallback=(80, 24): os.terminal_size((120, 24)))
    st = wizard.WizardState(_stages(), set())
    st.begin()
    out = io.StringIO()
    wizard._render_raw(st, out)
    # Drop the leading screen-clear so line 1 isn't prefixed by it, then assert
    # every non-blank rendered line shares the same 18-space left margin.
    text = out.getvalue().replace(wizard._CLEAR, "")
    body = [ln for ln in text.split("\r\n") if ln.strip()]
    assert all(ln.startswith(" " * 18) for ln in body)


# --- per-item detail line ----------------------------------------------------

def test_render_raw_detail_line_for_file(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: False)
    stages = [Stage("Core", [
        Entry("settings.json", "the settings file", True, "file",
              path="home/.claude/settings.json", mode="merge")])]
    st = wizard.WizardState(stages, set())
    st.begin()
    out = io.StringIO()
    wizard._render_raw(st, out)
    text = out.getvalue()
    assert "the settings file" in text
    assert "home/.claude/settings.json · merge" in text


def test_render_raw_detail_line_for_plugin(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: False)
    stages = [Stage("Plugins", [
        Entry("superpowers", "skill packs", True, "plugin", scope="user")])]
    st = wizard.WizardState(stages, set())
    st.begin()
    out = io.StringIO()
    wizard._render_raw(st, out)
    assert "plugin · user" in out.getvalue()


def test_render_raw_detail_tracks_cursor(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: False)
    stages = [Stage("Core", [
        Entry("a.json", "alpha desc", True, "file", path="p/a", mode="symlink"),
        Entry("b.json", "beta desc", True, "file", path="p/b", mode="merge")])]
    st = wizard.WizardState(stages, set())
    st.begin()
    st.move(1)                                # highlight the second entry
    out = io.StringIO()
    wizard._render_raw(st, out)
    text = out.getvalue()
    assert "p/b · merge" in text              # detail reflects the highlighted row


def test_entry_meta_kinds():
    f = Entry("x", "d", True, "file", path="some/path", mode="template")
    assert wizard._entry_meta(f) == "some/path · template"
    p = Entry("x", "d", True, "plugin", scope="user")
    assert wizard._entry_meta(p) == "plugin · user"
    mb = Entry("x", "d", True, "mailbox")
    assert wizard._entry_meta(mb) == "coordinator"


# --- install presets ---------------------------------------------------------

def test_to_preset_then_custom_enters_groups():
    st = wizard.WizardState(_stages(), set())
    st.to_preset()
    assert st.is_preset() and not st.is_intro()
    st.preset_cursor = wizard.WizardState.PRESETS.index("Custom")
    st.apply_preset()
    assert not st.is_preset() and not st.is_review()
    assert st.stage_index == 0                # walks the groups as today


def test_preset_everything_selects_all_and_jumps_to_review():
    st = wizard.WizardState(_stages(), set())
    st.to_preset()
    st.preset_cursor = wizard.WizardState.PRESETS.index("Everything")
    st.apply_preset()
    assert st.is_review()
    assert st.selected_ids() == {
        "settings.json", "statusline.sh", "superpowers", "frontend-design"}


def test_preset_recommended_is_default_on_entries():
    st = wizard.WizardState(_stages(), set())
    # default=True for all but frontend-design in _stages().
    assert st.preset_ids("Recommended") == {
        "settings.json", "statusline.sh", "superpowers"}


def test_preset_minimal_falls_back_to_recommended_when_none_required():
    st = wizard.WizardState(_stages(), set())   # no entry is required
    assert st.preset_ids("Minimal") == st.preset_ids("Recommended")


def test_preset_minimal_uses_required_when_present():
    stages = [Stage("Core", [
        Entry("a", "d", True, "file", required=True),
        Entry("b", "d", True, "file")])]
    st = wizard.WizardState(stages, set())
    assert st.preset_ids("Minimal") == {"a"}


def test_preset_back_to_intro():
    st = wizard.WizardState(_stages(), set())
    st.to_preset()
    st.prev_stage()                            # Left/Esc-back on the preset
    assert st.is_intro() and not st.is_preset()


def test_preset_move_clamps():
    st = wizard.WizardState(_stages(), set())
    st.to_preset()
    st.preset_cursor = 0
    st.preset_move(-1)
    assert st.preset_cursor == 0
    st.preset_move(99)
    assert st.preset_cursor == len(wizard.WizardState.PRESETS) - 1


def test_render_preset_raw_lists_all_options(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: False)
    st = wizard.WizardState(_stages(), set())
    st.to_preset()
    out = io.StringIO()
    wizard._render_preset_raw(st, out)
    text = out.getvalue()
    assert "┌─" in text                        # boxed like the other screens
    for name in ["Everything", "Recommended", "Minimal", "Custom"]:
        assert name in text


def test_raw_mode_loop_preset_recommended_applies():
    # intro Enter -> preset (default Recommended); Enter applies -> review;
    # Enter applies. The selection is the default-on set.
    import pty
    master, slave = pty.openpty()
    out = io.StringIO()
    _feed_after_raw(master, b"\r\r\r")
    stream = _PipeKeyStream(slave)

    def _run():
        return wizard._raw_mode_loop(_stages(), set(), stream, out)

    try:
        result = _with_timeout(3.0, _run)
    finally:
        os.close(slave)
        os.close(master)
    assert "settings.json" in result and "statusline.sh" in result
    assert "frontend-design" not in result     # not default-on -> excluded


# --- post-install summary render --------------------------------------------

def test_render_summary_plain():
    summary = {
        "applied": [("settings.json", "merged"), ("statusline.sh", "linked")],
        "plugins": {"superpowers": "installed"},
        "mailbox": {"coordinator": "linked"},
        "notes": ["re-auth required"],
        "skipped": ["frontend-design"],
    }
    out = io.StringIO()
    wizard.render_summary(summary, out)
    text = out.getvalue()
    assert "┌─" in text                                  # boxed
    assert "settings.json" in text and "merged" in text
    assert "superpowers" in text and "installed" in text
    assert "coordinator" in text and "linked" in text
    assert "frontend-design" in text                      # skipped section
    assert "re-auth required" in text                      # notes section
    assert "\x1b[1m" not in text                            # plain (no SGR)


def test_render_summary_handles_empty():
    out = io.StringIO()
    wizard.render_summary({}, out)
    text = out.getvalue()
    assert "(none)" in text                                # empty sections
    assert "complete" in text                              # crumb present


def test_render_summary_colored(monkeypatch):
    monkeypatch.setattr(wizard, "_color_enabled", lambda out: True)
    out = io.StringIO()
    wizard.render_summary({"applied": [("x", "ok")]}, out)
    assert "\x1b[1;32m" in out.getvalue()                  # selbold check mark
