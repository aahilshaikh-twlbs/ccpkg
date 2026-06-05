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
    lines = [ln for ln in out.getvalue().split("\r\n") if "DESC_" in ln]
    assert len(lines) == 2
    assert lines[0].index("DESC_A") == lines[1].index("DESC_B")


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
    assert "c c p k g" in text
    assert "environment-as-code" in text
    assert "2 stages" in text                                  # orientation line
    assert "begin" in text and "cancel" in text                # footer


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

    def _run():
        with pytest.raises((KeyboardInterrupt, OSError)):
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
            os.write(master_fd, bytes([b]))
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
    assert "c c p k g" in out.getvalue()        # intro splash was rendered


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
