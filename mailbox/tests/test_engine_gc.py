import os

from mailbox import config


def _join(engine, sid, label, cwd="/repo/a", board_name=None):
    """Join a session and return the join() result dict."""
    return engine.join(sid, label, cwd, board_name=board_name)


def test_gc_offlines_stale_live_session_and_reaps_its_auto_claims(engine, clock):
    # session-1 joins and acquires an auto-claim via check_write
    _join(engine, "s1", "alice")
    res = engine.check_write("s1", "/repo/a/foo.py")
    assert res["decision"] == "allow"
    auto_id = res["claim_id"]
    assert engine.claims[auto_id].kind == "auto"
    assert engine.claims[auto_id].released is False
    assert engine.presence["s1"].status == "active"

    # advance the clock past OFFLINE_GRACE without any heartbeat
    clock.t += config.OFFLINE_GRACE_SECONDS + 1

    counts = engine.gc()

    assert counts["presence_offlined"] == 1
    # the offlined session's auto claim is released
    assert engine.presence["s1"].status == "offline"
    assert engine.claims[auto_id].released is True
    # releasing the auto claim counts toward claims_reaped
    assert counts["claims_reaped"] >= 1


def test_gc_does_not_offline_session_still_within_grace(engine, clock):
    _join(engine, "s1", "alice")
    engine.check_write("s1", "/repo/a/foo.py")

    # capture the heartbeat set at join/check_write time so the assertion is
    # independent of where the fake clock starts.
    hb = engine.presence["s1"].last_heartbeat

    # advance past the stale threshold but NOT past offline grace
    clock.t += config.HEARTBEAT_STALE_SECONDS + 1

    # elapsed-since-heartbeat is past stale but still within offline grace
    elapsed = clock.t - hb
    assert config.HEARTBEAT_STALE_SECONDS < elapsed <= config.OFFLINE_GRACE_SECONDS

    counts = engine.gc()

    assert counts["presence_offlined"] == 0
    assert engine.presence["s1"].status == "active"


def test_gc_releases_expired_auto_claim(engine, clock):
    # s1 is kept live via an explicit heartbeat while its auto claim is
    # forced back to expired, isolating the gc auto-expiry branch.
    _join(engine, "s1", "alice")
    res = engine.check_write("s1", "/repo/a/foo.py")
    auto_id = res["claim_id"]
    assert engine.claims[auto_id].kind == "auto"

    # advance past AUTO_CLAIM_TTL but keep s1 live with a heartbeat first
    clock.t += config.AUTO_CLAIM_TTL_SECONDS + 1
    engine.heartbeat("s1")  # refreshes presence; also extends live auto claims
    # force the claim back to expired to isolate the gc expiry branch
    engine.claims[auto_id].expires = clock.t - 1

    counts = engine.gc()

    assert engine.claims[auto_id].released is True
    assert counts["claims_reaped"] >= 1


def test_gc_releases_claim_whose_holder_is_offline(engine, clock):
    _join(engine, "s1", "alice")
    # explicit claim with a long TTL so expiry is not the trigger
    c = engine.claim("s1", ["/repo/a/lib/**"], note="big refactor")
    claim_id = c["id"]
    assert engine.claims[claim_id].released is False

    # leave() marks s1 offline and releases its claims on a clean exit, so
    # instead simulate an unclean disappearance: flip status directly to offline
    engine.presence["s1"].status = "offline"

    counts = engine.gc()

    assert engine.claims[claim_id].released is True
    assert counts["claims_reaped"] >= 1


def test_gc_deletes_old_released_claim_file_and_dict(engine, clock):
    _join(engine, "s1", "alice")
    c = engine.claim("s1", ["/repo/a/x.py"])
    claim_id = c["id"]
    board = engine.claims[claim_id].board
    path = os.path.join(engine._board_dir(board), "claims", claim_id + ".json")
    assert os.path.exists(path)

    # release it, then age it past MESSAGE_RETENTION
    engine.release("s1", "all")
    assert engine.claims[claim_id].released is True
    clock.t += config.MESSAGE_RETENTION_SECONDS + 1

    counts = engine.gc()

    assert claim_id not in engine.claims
    assert not os.path.exists(path)
    assert counts["claims_reaped"] >= 1


def test_gc_deletes_old_read_message(engine, clock):
    # Use a single session so no co-location broadcast is created on join.
    # Only the one user-sent message exists, so messages_gc must equal 1.
    _join(engine, "s1", "alice")
    r = engine.send("s1", "*", "note", "hello board")
    msg_id = r["id"]
    board = engine.messages[msg_id].board
    path = os.path.join(engine._board_dir(board), "messages", msg_id + ".json")
    assert os.path.exists(path)

    clock.t += config.MESSAGE_RETENTION_SECONDS + 1

    counts = engine.gc()

    assert msg_id not in engine.messages
    assert not os.path.exists(path)
    assert counts["messages_gc"] == 1


def test_gc_deletes_old_offline_presence(engine, clock):
    _join(engine, "s1", "alice")
    sid_dir = engine.presence["s1"].boards[0]
    path = os.path.join(engine._board_dir(sid_dir), "presence", "s1.json")
    assert os.path.exists(path)

    # offline it well past the offline grace, then age past PRESENCE_RETENTION
    engine.presence["s1"].status = "offline"
    clock.t += config.PRESENCE_RETENTION_SECONDS + 1

    engine.gc()

    assert "s1" not in engine.presence
    assert not os.path.exists(path)


def test_ps_lists_co_board_sessions_with_status(engine, clock):
    _join(engine, "s1", "alice")
    _join(engine, "s2", "bob")
    # a session on a different cwd/board must NOT appear
    _join(engine, "s3", "carol", cwd="/other/repo")

    rows = engine.ps("s1")
    labels = {r["label"]: r for r in rows}
    # ps returns co-board sessions; carol is on a different board
    assert "carol" not in labels
    # both alice and bob are present (includes self per shared-board semantics)
    assert "bob" in labels
    bob = labels["bob"]
    assert bob["session_id"] == "s2"
    assert bob["status"] == "active"
    assert bob["last_seen_seconds"] >= 0
    assert isinstance(bob["boards"], list)
    assert set(bob.keys()) == {
        "session_id", "label", "cwd", "member", "status",
        "last_seen_seconds", "boards",
    }

    # make bob stale (past HEARTBEAT_STALE, within OFFLINE_GRACE)
    clock.t += config.HEARTBEAT_STALE_SECONDS + 1
    engine.heartbeat("s1")  # keep alice live
    rows = engine.ps("s1")
    labels = {r["label"]: r for r in rows}
    assert labels["bob"]["status"] == "stale"
    assert labels["alice"]["status"] == "active"

    # offline bob explicitly
    engine.presence["s2"].status = "offline"
    rows = engine.ps("s1")
    labels = {r["label"]: r for r in rows}
    assert labels["bob"]["status"] == "offline"


def test_whoami(engine, clock):
    _join(engine, "s1", "alice")
    who = engine.whoami("s1")
    assert who["exists"] is True
    assert who["session_id"] == "s1"
    assert who["label"] == "alice"
    assert who["status"] == "active"
    assert "boards" in who

    missing = engine.whoami("nope")
    assert missing["exists"] is False


def test_board_counts(engine, clock):
    _join(engine, "s1", "alice")
    _join(engine, "s2", "bob")
    engine.claim("s1", ["/repo/a/x.py"])
    engine.claim("s2", ["/repo/a/y.py"])

    data = engine.board("s1")
    assert "boards" in data
    assert len(data["boards"]) == 1
    b = data["boards"][0]
    assert set(b.keys()) == {"id", "origin", "name", "members", "claims"}
    assert b["members"] == 2
    assert b["claims"] == 2
