import subprocess
from unittest import mock

import pytest

from ccpkg.swarm import iterm


def test_spawn_tab_builds_correct_osascript(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["input"] = kwargs.get("input")
        result = mock.Mock()
        result.returncode = 0
        result.stdout = "PANE-ABC-123"
        result.stderr = ""
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    pane_id = iterm.spawn_tab(
        env={"FOO": "bar", "MAILBOX_BOARD": "swarm-x"},
        cmd="claude --dangerously-skip-permissions",
    )
    assert pane_id == "PANE-ABC-123"
    # osascript must include both env exports and the cmd
    osa = captured["input"]
    assert "FOO=bar" in osa
    assert "MAILBOX_BOARD=swarm-x" in osa
    assert "claude --dangerously-skip-permissions" in osa


def test_spawn_tab_raises_on_failure(monkeypatch):
    def fake_run(*a, **kw):
        result = mock.Mock()
        result.returncode = 1
        result.stdout = ""
        result.stderr = "permission denied"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(iterm.ITermError) as exc_info:
        iterm.spawn_tab({}, "noop")
    assert "permission denied" in str(exc_info.value)


def test_inject_writes_text_via_osascript(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["input"] = kwargs.get("input")
        result = mock.Mock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    iterm.inject("PANE-ABC", "hello world")
    assert "PANE-ABC" in captured["input"]
    assert "hello world" in captured["input"]


def test_close_panes_handles_empty():
    # No panes -> no error, no subprocess.
    iterm.close_panes([])  # should be a no-op


def test_close_panes_targets_each_pane(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(kwargs.get("input"))
        result = mock.Mock(); result.returncode = 0
        result.stdout = ""; result.stderr = ""
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    iterm.close_panes(["PANE-1", "PANE-2"])
    assert len(calls) == 2
    assert "PANE-1" in calls[0]
    assert "PANE-2" in calls[1]


def _capture_osa(monkeypatch, stdout=""):
    captured = {}

    def fake_run(args, **kwargs):
        captured["input"] = kwargs.get("input")
        result = mock.Mock()
        result.returncode = 0
        result.stdout = stdout
        result.stderr = ""
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def test_spawn_tab_cds_into_cwd_before_launch(monkeypatch):
    """Probe 2 finding: new tabs inherit the active session's cwd, so spawn_tab
    must cd into the target repo before launching claude."""
    captured = _capture_osa(monkeypatch, stdout="PANE-1")
    iterm.spawn_tab(env={"SWARM_ID": "x"}, cmd="claude", cwd="/repo/path")
    osa = captured["input"]
    assert "cd /repo/path" in osa
    # the cd must precede the launch command
    assert osa.index("cd /repo/path") < osa.index("claude")


def test_spawn_tab_without_cwd_has_no_cd(monkeypatch):
    captured = _capture_osa(monkeypatch, stdout="PANE-1")
    iterm.spawn_tab(env={}, cmd="claude")
    assert "cd " not in captured["input"]


def test_spawn_tab_settles_before_writing_command(monkeypatch):
    """Task 8 smoke finding: writing the launch command immediately on tab
    creation races the new tab's login-shell startup and garbles the command
    (observed `cd` -> `acd`). spawn_tab must let the shell settle first."""
    captured = _capture_osa(monkeypatch, stdout="PANE-1")
    iterm.spawn_tab(env={}, cmd="claude")
    osa = captured["input"]
    assert "delay" in osa
    assert osa.index("delay") < osa.index("write text")


def test_inject_addresses_session_by_iteration_not_id_lookup(monkeypatch):
    """Probe 2 finding: `tell session id "X"` fails (-1728). Must iterate
    windows/tabs/sessions and match `id of s`."""
    captured = _capture_osa(monkeypatch)
    iterm.inject("PANE-ABC", "hello")
    osa = captured["input"]
    assert "tell session id" not in osa          # the broken FORM A
    assert "id of s" in osa                        # FORM B: match by id
    assert "PANE-ABC" in osa


def test_inject_submits_with_separate_return(monkeypatch):
    """Probe 2 finding: write text's auto-newline is swallowed; submit needs a
    separate bare return after typing the text without a trailing newline."""
    captured = _capture_osa(monkeypatch)
    iterm.inject("PANE-ABC", "do the thing")
    osa = captured["input"]
    assert "newline no" in osa                     # type without auto-newline
    assert 'write text ""' in osa                  # separate return to submit


def test_close_panes_addresses_session_by_iteration(monkeypatch):
    captured = _capture_osa(monkeypatch)
    iterm.close_panes(["PANE-1"])
    osa = captured["input"]
    assert "tell session id" not in osa
    assert "id of s" in osa
    assert "PANE-1" in osa
