import json
from unittest import mock

import pytest

from ccpkg.swarm import launch


def test_refuses_nested_swarm(monkeypatch):
    monkeypatch.setenv("SWARM_LEAD", "lead-1")
    with pytest.raises(launch.NestedSwarmError):
        launch.launch_swarm(task="anything", subtasks={"lead-1": "x"})


def test_launches_one_tab_per_subtask_and_returns_swarm_id(monkeypatch, tmp_path):
    monkeypatch.delenv("SWARM_LEAD", raising=False)
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))

    spawn_calls = []

    def fake_spawn(env, cmd, cwd=None):
        spawn_calls.append({"env": dict(env), "cmd": cmd, "cwd": cwd})
        return "PANE-" + env["SWARM_LEAD"]

    inject_calls = []

    def fake_inject(pane_id, text):
        inject_calls.append({"pane_id": pane_id, "text": text})

    def fake_wait_presence(sid, lead, **kw):
        return True

    def fake_wait_all(sid, leads, **kw):
        return {l: {"status": "ok", "result_path":
                    str(tmp_path / sid / l / "result.md")} for l in leads}

    monkeypatch.setattr(launch.iterm, "spawn_tab", fake_spawn)
    monkeypatch.setattr(launch.iterm, "inject", fake_inject)
    monkeypatch.setattr(launch.lifecycle, "wait_for_presence", fake_wait_presence)
    monkeypatch.setattr(launch.lifecycle, "wait_for_all", fake_wait_all)

    # Seed result.md files so synthesize() can read them.
    for lead in ("lead-1", "lead-2"):
        d = tmp_path / "fakesid" / lead
        d.mkdir(parents=True)
        (d / "result.md").write_text(f"# {lead} done\n")

    sid = launch.launch_swarm(
        task="thing",
        subtasks={"lead-1": "x", "lead-2": "y"},
    )
    assert len(spawn_calls) == 2
    assert len(inject_calls) == 2
    # Each spawn must set SWARM_LEAD, SWARM_ID, SWARM_WORKDIR, MBOARD_BOARD
    for c in spawn_calls:
        e = c["env"]
        assert e["SWARM_ID"] == sid
        assert e["SWARM_LEAD"] in {"lead-1", "lead-2"}
        assert e["MBOARD_BOARD"] == "swarm-" + sid
        assert "SWARM_WORKDIR" in e
        # leads must launch in the orchestrator's repo, not the active tab's cwd
        assert c["cwd"] is not None

    # the injected kickoff must point each lead at its own inbox.md
    for c in inject_calls:
        assert "inbox.md" in c["text"]


def test_falls_back_to_b_assisted_when_osascript_fails(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SWARM_LEAD", raising=False)
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))

    def boom(env, cmd, cwd=None):
        raise launch.iterm.ITermError("automation denied")

    monkeypatch.setattr(launch.iterm, "spawn_tab", boom)
    monkeypatch.setattr(launch.lifecycle, "wait_for_all",
                        lambda *a, **k: {l: {"status": "timeout",
                                             "result_path": None}
                                         for l in a[1]})

    sid = launch.launch_swarm(
        task="thing",
        subtasks={"lead-1": "x"},
        fallback="assisted",
    )
    out = capsys.readouterr().out
    # B-assisted mode prints ready-to-paste commands for each lead.
    assert "MBOARD_BOARD=swarm-" in out
    assert "claude --dangerously-skip-permissions" in out
