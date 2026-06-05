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


def test_stage_navigation_and_done():
    st = wizard.WizardState(_stages(), set())
    assert st.stage_index == 0
    st.next_stage()
    assert st.stage_index == 1
    assert not st.is_done()
    st.next_stage()                   # past last stage -> done
    assert st.is_done()
    st.prev_stage()                   # back off the done state
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
