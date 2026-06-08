import json
import os
from pathlib import Path

import pytest

from ccpkg.swarm import workdir


def test_mint_swarm_id_format():
    sid = workdir.mint_swarm_id()
    # 8 hex chars from secrets.token_hex(4)
    assert len(sid) == 8
    assert all(c in "0123456789abcdef" for c in sid)


def test_mint_swarm_id_unique():
    assert workdir.mint_swarm_id() != workdir.mint_swarm_id()


def test_paths_are_under_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    assert workdir.root("abc123").startswith(str(tmp_path))
    assert workdir.lead_dir("abc123", "lead-1").startswith(workdir.root("abc123"))
    assert workdir.inbox_path("abc123", "lead-1").endswith("inbox.md")
    assert workdir.result_path("abc123", "lead-1").endswith("result.md")
    assert workdir.meta_path("abc123").endswith("meta.json")


def test_setup_creates_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    workdir.setup("abc123", leads=["lead-1", "lead-2", "lead-3"],
                  task="do the thing", inboxes={
                      "lead-1": "task A",
                      "lead-2": "task B",
                      "lead-3": "task C",
                  })
    root = tmp_path / "abc123"
    assert root.is_dir()
    expected = {"lead-1": "task A", "lead-2": "task B", "lead-3": "task C"}
    for lead in ("lead-1", "lead-2", "lead-3"):
        ld = root / lead
        assert ld.is_dir()
        assert (ld / "inbox.md").read_text() == expected[lead]
    meta = json.loads((root / "meta.json").read_text())
    assert meta["swarm_id"] == "abc123"
    assert meta["leads"] == ["lead-1", "lead-2", "lead-3"]
    assert meta["task"] == "do the thing"
    assert "created_at" in meta


def test_setup_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    args = ("abc123", ["lead-1"], "task", {"lead-1": "x"})
    workdir.setup(*args)
    workdir.setup(*args)  # should not raise
    assert (tmp_path / "abc123" / "lead-1" / "inbox.md").exists()


def test_list_swarms_returns_active(tmp_path, monkeypatch):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    workdir.setup("aaa", ["lead-1"], "t", {"lead-1": "x"})
    workdir.setup("bbb", ["lead-1"], "t", {"lead-1": "y"})
    swarms = workdir.list_swarms()
    assert {s["swarm_id"] for s in swarms} == {"aaa", "bbb"}


def test_record_pane_ids_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("CCPKG_SWARM_ROOT", str(tmp_path))
    workdir.setup("abc", ["lead-1", "lead-2"], "t",
                  {"lead-1": "x", "lead-2": "y"})
    workdir.record_pane_ids("abc", {"lead-1": "PID-1", "lead-2": "PID-2"})
    meta = json.loads((tmp_path / "abc" / "meta.json").read_text())
    assert meta["pane_ids"] == {"lead-1": "PID-1", "lead-2": "PID-2"}
