import os
import subprocess

import pytest

from mailbox import client, config, daemon


@pytest.fixture
def checkout(tmp_path):
    """A real git checkout so both sessions derive the SAME repo board."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(repo),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return str(repo)


@pytest.fixture
def live_daemon(tmp_home):
    """Spawn a real mailboxd on the temp socket; tear it down after the test."""
    client.ensure_running()
    # sanity: socket answers ping
    pong = client.request("ping")
    assert pong.get("ok") is True, pong
    assert pong.get("data") == "pong", pong
    yield
    # Best-effort shutdown: SIGTERM the spawned daemon. The daemon's own SIGTERM
    # handler (contract §10) unlinks the socket + pidfile on exit; the tmp_home
    # temp dirs are cleaned up by pytest after the test.
    info = daemon.read_pidfile()
    if info and daemon.pid_alive(info["pid"]):
        try:
            os.kill(info["pid"], 15)
        except OSError:
            pass


def _req(op, args=None):
    """Round-trip an op through the real socket; assert ok and return data."""
    resp = client.request(op, args or {})
    assert resp.get("ok") is True, (op, args, resp)
    return resp.get("data")


def test_e2e_multi_session(live_daemon, checkout):
    pa = os.path.join(checkout, "src", "auth.py")
    pb = os.path.join(checkout, "src", "auth.py")  # B targets the SAME path as A

    # --- Assertion 1: two sessions join the same checkout board; B sees co-location.
    da = _req("join", {"session_id": "sessA", "label": "alpha", "cwd": checkout})
    assert da["boards"], da
    repo_board = da["boards"][0]
    assert repo_board.startswith("repo-"), repo_board
    # A is first on the board -> nobody to be co-located with yet.
    assert da["colocated"] == {}, da

    db = _req("join", {"session_id": "sessB", "label": "beta", "cwd": checkout})
    assert db["boards"][0] == repo_board, db
    # B joining a board that already has live A -> co-location reported on B's join.
    assert repo_board in db["colocated"], db
    assert "alpha" in db["colocated"][repo_board], db

    # --- Assertion 2: A writes the path first -> allow, daemon records an auto-claim.
    ca = _req("check_write", {"session_id": "sessA", "abs_path": pa})
    assert ca["decision"] == "allow", ca
    assert "claim_id" in ca and ca["claim_id"], ca
    a_auto_claim = ca["claim_id"]

    # --- Assertion 3: B targets A's path while A is LIVE -> deny, with holder facts.
    cb = _req("check_write", {"session_id": "sessB", "abs_path": pb})
    assert cb["decision"] == "deny", cb
    assert cb["holder"] == "alpha", cb
    assert cb["holder_session"] == "sessA", cb
    assert cb["claim_id"] == a_auto_claim, cb
    assert isinstance(cb["since_seconds"], (int, float)), cb

    # --- Assertion 4: A leaves -> all A's claims released. B retry -> allow (clean).
    la = _req("leave", {"session_id": "sessA"})
    assert la["ok"] is True, la
    cb2 = _req("check_write", {"session_id": "sessB", "abs_path": pb})
    assert cb2["decision"] == "allow", cb2
    assert cb2["claim_id"] != a_auto_claim, cb2  # B's own fresh auto-claim, not A's

    # --- Assertion 5: A (now OFFLINE) re-stakes an explicit claim; B seizes it.
    # A is offline (left in Assertion 4); its explicit claim is unreleased but its
    # holder is not live, so seize must succeed without any wall-clock wait.
    pc = os.path.join(checkout, "src", "db.py")
    a_claim = _req("claim", {"session_id": "sessA", "globs": [pc], "note": "refactor"})
    assert a_claim["released"] is False, a_claim
    sz = _req("seize", {"session_id": "sessB", "abs_path": pc})
    assert "error" not in sz, sz
    assert a_claim["id"] in sz["seized"], sz
    assert sz["claim"]["session_id"] == "sessB", sz
    assert sz["claim"]["note"] == "seized", sz

    # --- Assertion 6: A rejoins, broadcasts a note; B reads it exactly once.
    _req("join", {"session_id": "sessA", "label": "alpha", "cwd": checkout})
    sent = _req(
        "send",
        {"session_id": "sessA", "to": "*", "kind": "note", "body": "heads up: touching auth"},
    )
    assert sent["id"].startswith("msg_"), sent

    inbox1 = _req("poll_inbox", {"session_id": "sessB"})
    bodies = [m["body"] for m in inbox1]
    assert "heads up: touching auth" in bodies, inbox1
    delivered = [m for m in inbox1 if m["body"] == "heads up: touching auth"]
    assert len(delivered) == 1, inbox1

    # Read receipt is GUARANTEED to suppress redelivery on the next poll.
    inbox2 = _req("poll_inbox", {"session_id": "sessB"})
    assert all(m["body"] != "heads up: touching auth" for m in inbox2), inbox2

    # --- Assertion 7: B's join queued a co-location broadcast; A can read it.
    inbox_a = _req("poll_inbox", {"session_id": "sessA"})
    coloc = [m for m in inbox_a if m["kind"] == "note" and m["from_session"] == "sessB"]
    assert coloc, inbox_a
    assert any("joined" in m["body"] for m in coloc), inbox_a

    # --- Assertion 8: everyone leaves; gc runs and reports its counters.
    _req("leave", {"session_id": "sessA"})
    _req("leave", {"session_id": "sessB"})
    # After clean leaves, all claims are released; check_write by an unknown session
    # fails open (no presence) -> allow, proving no stale territory blocks anyone.
    open_check = _req("check_write", {"session_id": "ghost", "abs_path": pa})
    assert open_check["decision"] == "allow", open_check

    g = _req("gc")
    assert set(g.keys()) == {"presence_offlined", "claims_reaped", "messages_gc"}, g
    assert all(isinstance(v, int) for v in g.values()), g
    # Precise expectations for THIS flow at the gc instant (runs in << 1s, so no
    # wall-clock threshold is crossed: HEARTBEAT_STALE=90s, OFFLINE_GRACE=180s,
    # MESSAGE_RETENTION=3600s, PRESENCE_RETENTION=86400s):
    #  - presence_offlined == 0: both sessA and sessB were already marked offline
    #    by their explicit leaves (Assertion 8), so gc's "live->offline past
    #    OFFLINE_GRACE" pass skips them; no live session crossed the grace window.
    #  - claims_reaped == 0: every claim is already released — A's auto-claim and
    #    explicit claim (released by leave + seize), B's auto- and seized claims
    #    (released by B's leave). None are old enough (> MESSAGE_RETENTION since
    #    created) to be deleted, none are unreleased-auto-expired, and the
    #    "holder offline -> release" rule only fires on UNRELEASED claims (there
    #    are none). So nothing is reaped — this guards against over-reaping recent
    #    state and confirms offline-held claims were already released cleanly.
    #  - messages_gc == 0: all messages were created milliseconds ago, far under
    #    MESSAGE_RETENTION.
    assert g["presence_offlined"] == 0, g
    assert g["claims_reaped"] == 0, g
    assert g["messages_gc"] == 0, g


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("MAILBOX_E2E_SLOW") != "1",
    reason="real-time staleness: set MAILBOX_E2E_SLOW=1 to run (waits >HEARTBEAT_STALE_SECONDS)",
)
def test_e2e_stale_warn_realtime(live_daemon, checkout):
    import time

    pa = os.path.join(checkout, "src", "svc.py")
    _req("join", {"session_id": "sessA", "label": "alpha", "cwd": checkout})
    _req("join", {"session_id": "sessB", "label": "beta", "cwd": checkout})

    # A stakes the path (auto-claim via check_write), then NEVER heartbeats.
    assert _req("check_write", {"session_id": "sessA", "abs_path": pa})["decision"] == "allow"

    # SLOW: real wall-clock wait until A's heartbeat is older than HEARTBEAT_STALE_SECONDS.
    # This is the only sub-case that cannot be made deterministic over a wall-clock
    # daemon (the socket gives no clock injection); it is therefore env-gated above.
    time.sleep(config.HEARTBEAT_STALE_SECONDS + 1)

    # A's claim is now stale-but-unreleased -> B's write is WARNed, not denied.
    cb = _req("check_write", {"session_id": "sessB", "abs_path": pa})
    assert cb["decision"] == "warn", cb
    assert cb["holder"] == "alpha", cb
    assert cb["claim_id"], cb
    assert isinstance(cb["stale_seconds"], (int, float)), cb
