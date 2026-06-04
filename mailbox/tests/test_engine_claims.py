from mailbox import config


def _join(engine, sid, label, cwd):
    return engine.join(sid, label, cwd)


def test_claim_creates_explicit_claim_on_repo_board(engine, clock):
    clock.t = 1000.0
    info = _join(engine, "s1", "alice", "/repo")
    repo_board = info["boards"][0]

    result = engine.claim("s1", ["/repo/src/auth/**"], note="big refactor")

    assert result["id"].startswith("clm_")
    assert result["board"] == repo_board
    assert result["session_id"] == "s1"
    assert result["label"] == "alice"
    assert result["paths"] == ["/repo/src/auth/**"]
    assert result["kind"] == "explicit"
    assert result["note"] == "big refactor"
    assert result["released"] is False
    assert result["created"] == 1000.0
    assert result["expires"] == 1000.0 + config.EXPLICIT_CLAIM_TTL_SECONDS
    # persisted in memory
    assert engine.claims[result["id"]].paths == ["/repo/src/auth/**"]


def test_claim_auto_kind_uses_short_ttl(engine, clock):
    clock.t = 2000.0
    _join(engine, "s1", "alice", "/repo")

    result = engine.claim("s1", ["/repo/a.py"], kind="auto")

    assert result["kind"] == "auto"
    assert result["expires"] == 2000.0 + config.AUTO_CLAIM_TTL_SECONDS


def test_claim_multiple_globs_recorded(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")

    result = engine.claim("s1", ["/repo/a/**", "/repo/b.py"])

    assert result["paths"] == ["/repo/a/**", "/repo/b.py"]


def test_explicit_claim_then_conflicting_write_from_other_session_denied(engine, clock):
    clock.t = 1000.0
    a = _join(engine, "s1", "alice", "/repo")
    b = _join(engine, "s2", "bob", "/repo")
    # both sessions share the same repo board
    assert a["boards"][0] == b["boards"][0]

    engine.claim("s1", ["/repo/src/auth/**"], note="hands off")

    # s1 is live (heartbeat at join == now); s2 attempts a write inside the claim
    decision = engine.check_write("s2", "/repo/src/auth/login.py")

    assert decision["decision"] == "deny"
    assert decision["holder"] == "alice"
    assert decision["holder_session"] == "s1"
    assert decision["note"] == "hands off"


def test_release_all_releases_every_claim_of_session(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])
    c2 = engine.claim("s1", ["/repo/b.py"])

    result = engine.release("s1", "all")

    assert set(result["released"]) == {c1["id"], c2["id"]}
    assert engine.claims[c1["id"]].released is True
    assert engine.claims[c2["id"]].released is True


def test_release_by_claim_id(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])
    c2 = engine.claim("s1", ["/repo/b.py"])

    result = engine.release("s1", c1["id"])

    assert result["released"] == [c1["id"]]
    assert engine.claims[c1["id"]].released is True
    assert engine.claims[c2["id"]].released is False


def test_release_by_glob_string(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**", "/repo/x.py"])
    c2 = engine.claim("s1", ["/repo/b.py"])

    result = engine.release("s1", "/repo/a/**")

    assert result["released"] == [c1["id"]]
    assert engine.claims[c1["id"]].released is True
    assert engine.claims[c2["id"]].released is False


def test_release_by_id_not_owned_is_refused_without_force(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])

    result = engine.release("s2", c1["id"])

    assert result["released"] == []
    assert engine.claims[c1["id"]].released is False


def test_release_by_id_not_owned_with_force(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])

    result = engine.release("s2", c1["id"], force=True)

    assert result["released"] == [c1["id"]]
    assert engine.claims[c1["id"]].released is True


def test_release_all_does_not_touch_other_sessions(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])
    c2 = engine.claim("s2", ["/repo/b.py"])

    result = engine.release("s1", "all")

    assert result["released"] == [c1["id"]]
    assert engine.claims[c2["id"]].released is False


def test_seize_fails_when_holder_is_live(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    c1 = engine.claim("s1", ["/repo/src/auth/**"])

    # s1 is live (heartbeat at join == 1000); no clock advance
    result = engine.seize("s2", "/repo/src/auth/login.py")

    assert result == {"error": "holder-live", "holder": "alice"}
    assert engine.claims[c1["id"]].released is False


def test_seize_succeeds_when_holder_is_stale(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    c1 = engine.claim("s1", ["/repo/src/auth/**"])

    # advance past the stale threshold so s1 is no longer live
    clock.t = 1000.0 + config.HEARTBEAT_STALE_SECONDS + 1.0

    result = engine.seize("s2", "/repo/src/auth/login.py")

    assert result["seized"] == [c1["id"]]
    assert engine.claims[c1["id"]].released is True
    claim = result["claim"]
    assert claim["session_id"] == "s2"
    assert claim["label"] == "bob"
    assert claim["paths"] == ["/repo/src/auth/login.py"]
    assert claim["kind"] == "explicit"
    assert claim["note"] == "seized"
    assert claim["released"] is False
    # new claim is recorded
    assert engine.claims[claim["id"]].session_id == "s2"


def test_seize_ignores_own_and_released_claims(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    # s2's own claim should not block its seize, and no other holder exists
    engine.claim("s2", ["/repo/src/auth/**"])

    result = engine.seize("s2", "/repo/src/auth/login.py")

    assert "error" not in result
    assert result["seized"] == []
    assert result["claim"]["session_id"] == "s2"
    assert result["claim"]["note"] == "seized"


def test_list_claims_scope_board(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])
    c2 = engine.claim("s2", ["/repo/b.py"])

    result = engine.list_claims("s1", scope="board")

    ids = {c["id"] for c in result}
    # both claims are on s1's repo board
    assert ids == {c1["id"], c2["id"]}


def test_list_claims_scope_mine(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])
    engine.claim("s2", ["/repo/b.py"])

    result = engine.list_claims("s1", scope="mine")

    ids = {c["id"] for c in result}
    assert ids == {c1["id"]}


def test_list_claims_scope_all_includes_other_boards(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo-a")
    _join(engine, "s2", "bob", "/repo-b")
    c1 = engine.claim("s1", ["/repo-a/x.py"])
    c2 = engine.claim("s2", ["/repo-b/y.py"])

    # s1 and s2 are on different repo boards
    board_scope = engine.list_claims("s1", scope="board")
    assert {c["id"] for c in board_scope} == {c1["id"]}

    all_scope = engine.list_claims("s1", scope="all")
    assert {c["id"] for c in all_scope} == {c1["id"], c2["id"]}


def test_list_claims_excludes_released(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])
    engine.release("s1", c1["id"])

    result = engine.list_claims("s1", scope="all")

    assert result == []


def test_list_claims_annotates_active(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])

    result = engine.list_claims("s1", scope="mine")

    assert len(result) == 1
    entry = result[0]
    assert entry["id"] == c1["id"]
    assert entry["live"] is True
    assert entry["holder_status"] == "active"


def test_list_claims_annotates_stale(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    engine.claim("s1", ["/repo/a/**"])

    # advance so s1's heartbeat is stale but presence still status=="active"
    clock.t = 1000.0 + config.HEARTBEAT_STALE_SECONDS + 1.0

    result = engine.list_claims("s2", scope="board")

    entry = [c for c in result if c["session_id"] == "s1"][0]
    assert entry["live"] is False
    assert entry["holder_status"] == "stale"


def test_list_claims_annotates_offline(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    _join(engine, "s2", "bob", "/repo")
    c1 = engine.claim("s1", ["/repo/a/**"])
    # mark s1 offline directly (simulating a flipped presence)
    engine.presence["s1"].status = "offline"

    result = engine.list_claims("s2", scope="board")

    entry = [c for c in result if c["id"] == c1["id"]][0]
    assert entry["live"] is False
    assert entry["holder_status"] == "offline"
