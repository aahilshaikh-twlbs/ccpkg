import json
import sys

import pytest

from ccpkg.swarm import cli


def test_cli_status_lists_active_swarms(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    from ccpkg.swarm import workdir
    workdir.setup("aaa", ["lead-1"], "task A", {"lead-1": "x"})
    workdir.setup("bbb", ["lead-1", "lead-2"], "task B",
                  {"lead-1": "x", "lead-2": "y"})
    rc = cli.main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "aaa" in out
    assert "bbb" in out


def test_cli_close_calls_iterm_close(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    from ccpkg.swarm import workdir
    workdir.setup("aaa", ["lead-1"], "task",
                  {"lead-1": "x"})
    workdir.record_pane_ids("aaa", {"lead-1": "PANE-1"})

    closed = []
    def fake_close(ids):
        closed.extend(ids)

    monkeypatch.setattr(cli.iterm, "close_panes", fake_close)
    rc = cli.main(["close", "aaa"])
    assert rc == 0
    assert closed == ["PANE-1"]


def test_cli_close_no_id_closes_all(monkeypatch, tmp_path):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    from ccpkg.swarm import workdir
    workdir.setup("aaa", ["lead-1"], "task", {"lead-1": "x"})
    workdir.record_pane_ids("aaa", {"lead-1": "PANE-A"})
    workdir.setup("bbb", ["lead-1"], "task", {"lead-1": "x"})
    workdir.record_pane_ids("bbb", {"lead-1": "PANE-B"})

    closed = []
    monkeypatch.setattr(cli.iterm, "close_panes",
                        lambda ids: closed.extend(ids))
    rc = cli.main(["close"])
    assert rc == 0
    assert set(closed) == {"PANE-A", "PANE-B"}


def test_cli_sweep_removes_workdirs(monkeypatch, tmp_path):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    from ccpkg.swarm import workdir
    workdir.setup("old", ["lead-1"], "task", {"lead-1": "x"})
    rc = cli.main(["sweep"])
    assert rc == 0
    assert not (tmp_path / "old").exists()


def test_cli_launch_calls_orchestrator(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    captured = {}

    def fake_launch(**kw):
        captured.update(kw)
        return "fakeid"

    monkeypatch.setattr(cli.launch, "launch_swarm", fake_launch)
    payload = json.dumps({
        "task": "do X",
        "subtasks": {"lead-1": "alpha", "lead-2": "beta"},
    })
    rc = cli.main(["launch", "--payload", payload])
    assert rc == 0
    assert captured["task"] == "do X"
    assert captured["subtasks"] == {"lead-1": "alpha", "lead-2": "beta"}
