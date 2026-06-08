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
