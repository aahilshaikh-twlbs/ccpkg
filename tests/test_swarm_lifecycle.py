import json

from ccpkg.swarm import lifecycle


class DaemonFake:
    """Models the REAL mailbox daemon contract (mailbox/src/mailbox/engine.py):

    - `ps`/`poll_inbox` require a `session_id` and derive boards from THAT
      session's own presence; they ignore a `board` kwarg (protocol.py strips
      any arg not in the per-op allowlist).
    - `send` routes to the sender's primary (last-joined) board.

    The previous fake accepted a `board` kwarg and returned everything, which is
    why the lifecycle board-arg bug shipped undetected. This fake refuses calls
    that don't carry a valid `session_id`, so the orchestrator MUST join the
    swarm board and poll with its own session_id.
    """

    def __init__(self):
        self.presence = {}   # session_id -> {label, status, boards}
        self.messages = []   # {kind, body, board, from_session}

    def _boards(self, session_id):
        return set(self.presence.get(session_id, {}).get("boards", []))

    def request(self, op, args=None):
        args = args or {}
        if op == "join":
            sid = args["session_id"]
            boards = ["repo-board"]
            if args.get("board_name"):
                boards.append("named-" + args["board_name"])
            self.presence[sid] = {
                "label": args.get("label", sid),
                "status": "active",
                "boards": boards,
            }
            return {"ok": True, "data": {"boards": boards,
                                         "label": args.get("label", sid)}}
        if op == "ps":
            sid = args.get("session_id")
            if not sid or sid not in self.presence:
                return {"ok": False, "error": "TypeError: missing session_id"}
            mine = self._boards(sid)
            rows = [p for p in self.presence.values()
                    if mine & set(p["boards"])]
            return {"ok": True, "data": rows}
        if op == "poll_inbox":
            sid = args.get("session_id")
            if not sid or sid not in self.presence:
                return {"ok": False, "error": "TypeError: missing session_id"}
            mine = self._boards(sid)
            return {"ok": True, "data": [m for m in self.messages
                                         if m["board"] in mine
                                         and m["from_session"] != sid]}
        return {"ok": False, "error": "unknown op"}

    # test helpers --------------------------------------------------------
    def add_lead_presence(self, swarm_id, lead, status="active"):
        sid = "sess-" + lead
        self.presence[sid] = {
            "label": "swarm-" + swarm_id + "-" + lead,
            "status": status,
            "boards": ["repo-board", "named-swarm-" + swarm_id],
        }

    def add_done(self, swarm_id, lead, status="ok", result_path="/r",
                 kind="swarm_done"):
        self.messages.append({
            "kind": kind,
            "body": json.dumps({"lead": lead, "status": status,
                                "result_path": result_path}),
            "board": "named-swarm-" + swarm_id,
            "from_session": "sess-" + lead,
        })


def test_wait_for_presence_returns_when_active(monkeypatch):
    fake = DaemonFake()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    fake.add_lead_presence("abc", "lead-1", status="active")
    assert lifecycle.wait_for_presence("abc", "lead-1", timeout=1) is True


def test_wait_for_presence_times_out_when_no_presence(monkeypatch):
    fake = DaemonFake()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    assert lifecycle.wait_for_presence("abc", "lead-1", timeout=0.5) is False


def test_wait_for_presence_ignores_stale_lead(monkeypatch):
    fake = DaemonFake()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    fake.add_lead_presence("abc", "lead-1", status="stale")
    assert lifecycle.wait_for_presence("abc", "lead-1", timeout=0.5) is False


def test_orchestrator_joins_swarm_board_before_polling(monkeypatch):
    """The orchestrator must establish its own presence on the swarm board so
    ps/poll_inbox (which derive boards from the caller) can see the leads."""
    fake = DaemonFake()
    joins = []
    orig = fake.request

    def spy(op, args=None):
        if op == "join":
            joins.append(args)
        return orig(op, args)

    fake.request = spy
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    lifecycle.wait_for_presence("abc", "lead-1", timeout=0.3)
    assert any(j.get("board_name") == "swarm-abc" for j in joins)


def test_poll_done_returns_swarm_done_messages(monkeypatch):
    fake = DaemonFake()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    fake.add_done("abc", "lead-1", result_path="/tmp/a")
    dones = lifecycle.poll_done("abc")
    assert len(dones) == 1
    assert dones[0]["lead"] == "lead-1"
    assert dones[0]["status"] == "ok"


def test_poll_done_ignores_non_done_kinds(monkeypatch):
    fake = DaemonFake()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    fake.add_done("abc", "lead-1", kind="note")  # not a swarm_done
    assert lifecycle.poll_done("abc") == []


def test_wait_for_all_collects_all_then_returns(monkeypatch):
    fake = DaemonFake()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    stage = {"n": 0}

    def step(_):
        stage["n"] += 1
        if stage["n"] >= 2:
            fake.add_done("abc", "lead-1", result_path="/r1")
            fake.add_done("abc", "lead-2", result_path="/r2")

    monkeypatch.setattr(lifecycle.time, "sleep", step)
    results = lifecycle.wait_for_all("abc", ["lead-1", "lead-2"], timeout=5)
    assert set(results.keys()) == {"lead-1", "lead-2"}
    assert results["lead-1"]["status"] == "ok"


def test_wait_for_all_times_out_with_partial_results(monkeypatch):
    fake = DaemonFake()
    monkeypatch.setattr(lifecycle, "_mailbox_client", lambda: fake)
    fake.add_done("abc", "lead-1", result_path="/r1")
    results = lifecycle.wait_for_all("abc", ["lead-1", "lead-2"], timeout=0.5,
                                     poll_interval=0.1)
    assert results["lead-1"]["status"] == "ok"
    assert results["lead-2"]["status"] == "timeout"
