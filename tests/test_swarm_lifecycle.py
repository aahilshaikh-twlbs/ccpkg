import json
import time

import pytest

from ccpkg.swarm import lifecycle


class FakeMailbox:
    """Minimal stand-in for mailbox.client.request."""
    def __init__(self):
        self.presence = {}  # session_id -> {"label", "status"}
        self.messages = []  # list of {"kind", "body", "from_label", "board"}

    def request(self, op, args=None):
        args = args or {}
        if op == "ps":
            board = args.get("board")
            data = list(self.presence.values())
            return {"ok": True, "data": data}
        if op == "poll_inbox":
            sid = args.get("session_id")
            return {"ok": True, "data": list(self.messages)}
        return {"ok": False, "error": "unknown op"}


def test_wait_for_presence_returns_when_active(monkeypatch):
    fake = FakeMailbox()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    # Lead becomes active before timeout
    fake.presence["s1"] = {"label": "swarm-abc-lead-1", "status": "active"}
    assert lifecycle.wait_for_presence("abc", "lead-1", timeout=1) is True


def test_wait_for_presence_times_out(monkeypatch):
    fake = FakeMailbox()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    # No presence ever
    assert lifecycle.wait_for_presence("abc", "lead-1", timeout=0.5) is False


def test_poll_done_returns_swarm_done_messages(monkeypatch):
    fake = FakeMailbox()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    fake.messages = [
        {"kind": "note", "body": "irrelevant", "from_label": "x", "board": "swarm-abc"},
        {"kind": "swarm_done",
         "body": json.dumps({"lead": "lead-1", "status": "ok",
                             "result_path": "/tmp/a"}),
         "from_label": "swarm-abc-lead-1",
         "board": "swarm-abc"},
    ]
    dones = lifecycle.poll_done("abc")
    assert len(dones) == 1
    assert dones[0]["lead"] == "lead-1"
    assert dones[0]["status"] == "ok"


def test_wait_for_all_collects_all_then_returns(monkeypatch):
    fake = FakeMailbox()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    # Stage 1: only lead-1 done; Stage 2: both done.
    stage = {"n": 0}

    def step(_):
        stage["n"] += 1
        if stage["n"] >= 2:
            fake.messages = [
                {"kind": "swarm_done",
                 "body": json.dumps({"lead": "lead-1", "status": "ok",
                                     "result_path": "/r1"}),
                 "from_label": "x", "board": "swarm-abc"},
                {"kind": "swarm_done",
                 "body": json.dumps({"lead": "lead-2", "status": "ok",
                                     "result_path": "/r2"}),
                 "from_label": "y", "board": "swarm-abc"},
            ]

    monkeypatch.setattr(lifecycle.time, "sleep", step)
    results = lifecycle.wait_for_all("abc", ["lead-1", "lead-2"], timeout=5)
    assert set(results.keys()) == {"lead-1", "lead-2"}


def test_wait_for_all_times_out_with_partial_results(monkeypatch):
    fake = FakeMailbox()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    fake.messages = [
        {"kind": "swarm_done",
         "body": json.dumps({"lead": "lead-1", "status": "ok",
                             "result_path": "/r1"}),
         "from_label": "x", "board": "swarm-abc"},
    ]
    # No further sleep advances; we just iterate quickly.
    results = lifecycle.wait_for_all("abc", ["lead-1", "lead-2"], timeout=0.5,
                                     poll_interval=0.1)
    assert "lead-1" in results
    assert results["lead-2"]["status"] == "timeout"
