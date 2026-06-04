import os

from mailbox import config
from mailbox.matching import path_matches


def _join_two(engine, cwd):
    engine.join("sessA", "alice", cwd)
    engine.join("sessB", "bob", cwd)


def test_first_write_allows_and_creates_auto_claim(engine, tmp_path):
    cwd = str(tmp_path)
    engine.join("sessA", "alice", cwd)
    fp = os.path.join(cwd, "src", "app.py")

    res = engine.check_write("sessA", fp)

    assert res["decision"] == "allow"
    assert res["claim_id"].startswith("clm_")
    claim = engine.claims[res["claim_id"]]
    assert claim.session_id == "sessA"
    assert claim.kind == "auto"
    assert claim.board == engine._repo_board("sessA")
    assert fp in claim.paths


def test_auto_claim_dedups_and_refreshes_expiry(engine, tmp_path, clock):
    cwd = str(tmp_path)
    engine.join("sessA", "alice", cwd)
    fp = os.path.join(cwd, "src", "app.py")

    first = engine.check_write("sessA", fp)
    claim_id = first["claim_id"]
    first_expiry = engine.claims[claim_id].expires

    clock.t += 10
    second = engine.check_write("sessA", fp)

    # same auto-claim reused, path not duplicated, expiry refreshed forward
    assert second["claim_id"] == claim_id
    assert engine.claims[claim_id].paths.count(fp) == 1
    assert engine.claims[claim_id].expires == clock.t + config.AUTO_CLAIM_TTL_SECONDS
    assert engine.claims[claim_id].expires > first_expiry


def test_second_write_appends_distinct_path_to_same_claim(engine, tmp_path):
    cwd = str(tmp_path)
    engine.join("sessA", "alice", cwd)
    fp1 = os.path.join(cwd, "src", "a.py")
    fp2 = os.path.join(cwd, "src", "b.py")

    r1 = engine.check_write("sessA", fp1)
    r2 = engine.check_write("sessA", fp2)

    assert r1["claim_id"] == r2["claim_id"]
    claim = engine.claims[r2["claim_id"]]
    assert fp1 in claim.paths
    assert fp2 in claim.paths


def test_live_conflict_denies(engine, tmp_path):
    cwd = str(tmp_path)
    _join_two(engine, cwd)
    fp = os.path.join(cwd, "src", "shared.py")

    a = engine.check_write("sessA", fp)
    assert a["decision"] == "allow"

    b = engine.check_write("sessB", fp)
    assert b["decision"] == "deny"
    assert b["holder"] == "alice"
    assert b["holder_session"] == "sessA"
    assert b["claim_id"] == a["claim_id"]
    assert b["since_seconds"] >= 0
    assert "note" in b


def test_stale_conflict_warns(engine, tmp_path, clock):
    cwd = str(tmp_path)
    _join_two(engine, cwd)
    fp = os.path.join(cwd, "src", "shared.py")

    engine.check_write("sessA", fp)
    # advance past stale threshold so A's presence is no longer live
    clock.t += config.HEARTBEAT_STALE_SECONDS + 1

    b = engine.check_write("sessB", fp)
    assert b["decision"] == "warn"
    assert b["holder"] == "alice"
    assert b["claim_id"] == engine.claims[b["claim_id"]].id
    assert b["stale_seconds"] >= config.HEARTBEAT_STALE_SECONDS


def test_different_path_allows_after_stale_conflict(engine, tmp_path, clock):
    cwd = str(tmp_path)
    _join_two(engine, cwd)
    shared = os.path.join(cwd, "src", "shared.py")
    other = os.path.join(cwd, "src", "other.py")

    engine.check_write("sessA", shared)
    clock.t += config.HEARTBEAT_STALE_SECONDS + 1

    b = engine.check_write("sessB", other)
    assert b["decision"] == "allow"
    assert b["claim_id"].startswith("clm_")
    bclaim = engine.claims[b["claim_id"]]
    assert bclaim.session_id == "sessB"
    assert other in bclaim.paths


def test_no_presence_fails_open(engine, tmp_path):
    fp = os.path.join(str(tmp_path), "x.py")
    res = engine.check_write("ghost", fp)
    assert res == {"decision": "allow", "reason": "no-presence"}


def test_conflict_scope_is_only_shared_boards(engine, tmp_path):
    # A and B are in DIFFERENT checkouts -> different repo boards -> no conflict
    cwd_a = str(tmp_path / "repoA")
    cwd_b = str(tmp_path / "repoB")
    os.makedirs(cwd_a)
    os.makedirs(cwd_b)
    engine.join("sessA", "alice", cwd_a)
    engine.join("sessB", "bob", cwd_b)
    # identical relative file name, but distinct absolute paths under distinct boards
    a = engine.check_write("sessA", os.path.join(cwd_a, "f.py"))
    b = engine.check_write("sessB", os.path.join(cwd_b, "f.py"))
    assert a["decision"] == "allow"
    assert b["decision"] == "allow"
    assert path_matches  # imported symbol is used by engine; sanity reference
