import os

from mailbox.engine import MailboxEngine
from mailbox import config


def test_init_empty_state(engine, clock):
    assert engine.boards == {}
    assert engine.presence == {}
    assert engine.claims == {}
    assert engine.messages == {}
    assert engine._now() == clock.t


from mailbox.models import Presence, Claim, Message


def _mk_presence(session_id, label, cwd, board_list, t):
    return Presence(
        session_id=session_id,
        label=label,
        cwd=cwd,
        boards=list(board_list),
        joined=t,
        last_heartbeat=t,
        status="active",
    )


def test_ensure_board_persists_meta(engine, clock):
    engine._ensure_board("repo-abc", "/repo", name=None)
    meta_path = os.path.join(engine._board_dir("repo-abc"), "meta.json")
    assert os.path.exists(meta_path)
    assert engine.boards["repo-abc"]["origin"] == "/repo"
    assert engine.boards["repo-abc"]["name"] is None
    assert engine.boards["repo-abc"]["created"] == clock.t
    before = dict(engine.boards["repo-abc"])
    clock.t += 50
    engine._ensure_board("repo-abc", "/repo", name=None)
    assert engine.boards["repo-abc"] == before  # idempotent, not re-created


def test_persist_helpers_roundtrip_via_reload(engine, clock):
    engine._ensure_board("named-x", "named:x", name="x")
    p = _mk_presence("s1", "alice", "/repo", ["named-x"], clock.t)
    engine.presence["s1"] = p
    engine._persist_presence(p)
    c = Claim(id="clm_a", board="named-x", session_id="s1", label="alice",
              paths=["/repo/a.py"], kind="auto", created=clock.t,
              expires=clock.t + 300)
    engine.claims["clm_a"] = c
    engine._persist_claim(c)
    m = Message(id="msg_a", board="named-x", from_session="s1",
                from_label="alice", to="*", kind="note", body="hi",
                created=clock.t)
    engine.messages["msg_a"] = m
    engine._persist_message(m)

    reloaded = MailboxEngine(engine.state_dir, now_fn=lambda: clock.t)
    assert reloaded.presence["s1"].label == "alice"
    assert reloaded.claims["clm_a"].paths == ["/repo/a.py"]
    assert reloaded.messages["msg_a"].body == "hi"
    assert reloaded.boards["named-x"]["name"] == "x"


def test_is_live(engine, clock):
    p = _mk_presence("s1", "alice", "/repo", ["repo-x"], clock.t)
    assert engine._is_live(p) is True
    clock.t += config.HEARTBEAT_STALE_SECONDS + 1
    assert engine._is_live(p) is False  # stale
    p.status = "offline"
    p.last_heartbeat = clock.t
    assert engine._is_live(p) is False  # offline never live


def test_repo_and_primary_board(engine, clock):
    p = _mk_presence("s1", "alice", "/repo", ["repo-x", "named-y"], clock.t)
    engine.presence["s1"] = p
    assert engine._repo_board("s1") == "repo-x"
    assert engine._primary_board("s1") == "named-y"
    p2 = _mk_presence("s2", "bob", "/repo", ["repo-x"], clock.t)
    engine.presence["s2"] = p2
    assert engine._primary_board("s2") == "repo-x"


import mailbox.engine as engine_mod


def _stub_repo_board(monkeypatch, board_id="repo-r1", origin="/repo"):
    monkeypatch.setattr(engine_mod.boards_mod, "derive_repo_board",
                        lambda cwd: (board_id, origin))


def test_join_creates_presence_and_repo_board(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    out = engine.join("s1", "alice", "/repo")
    assert out["label"] == "alice"
    assert out["boards"] == ["repo-r1"]
    assert out["colocated"] == {}
    p = engine.presence["s1"]
    assert p.status == "active"
    assert p.boards == ["repo-r1"]
    assert p.joined == clock.t
    assert p.last_heartbeat == clock.t
    assert "repo-r1" in engine.boards
    # presence persisted under repo board
    ppath = os.path.join(engine._board_dir("repo-r1"), "presence", "s1.json")
    assert os.path.exists(ppath)


def test_join_with_board_name_appends_named_board(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    monkeypatch.setattr(engine_mod.boards_mod, "board_id_for_name",
                        lambda name: "named-effort")
    out = engine.join("s1", "alice", "/repo", board_name="effort")
    assert out["boards"] == ["repo-r1", "named-effort"]
    assert engine.presence["s1"].boards == ["repo-r1", "named-effort"]
    assert "named-effort" in engine.boards


def test_join_preserves_joined_on_rejoin(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    engine.join("s1", "alice", "/repo")
    first_joined = engine.presence["s1"].joined
    clock.t += 100
    engine.join("s1", "alice2", "/repo")
    p = engine.presence["s1"]
    assert p.joined == first_joined      # joined preserved
    assert p.label == "alice2"           # label updated
    assert p.last_heartbeat == clock.t   # heartbeat refreshed


def test_second_join_broadcasts_colocation_note(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    engine.join("s1", "alice", "/repo")
    assert len(engine.messages) == 0          # first join: no other members
    out2 = engine.join("s2", "bob", "/repo")
    assert out2["colocated"] == {"repo-r1": ["alice"]}
    notes = [m for m in engine.messages.values() if m.kind == "note"]
    assert len(notes) == 1
    note = notes[0]
    assert note.from_session == "s2"
    assert note.to == "*"
    assert note.board == "repo-r1"
    assert note.body == ("bob joined checkout — 2 now active; "
                         "coordinate via mailbox")
    # note persisted
    npath = os.path.join(engine._board_dir("repo-r1"), "messages",
                         note.id + ".json")
    assert os.path.exists(npath)


def test_active_rejoin_does_not_rebroadcast(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    engine.join("s1", "alice", "/repo")
    engine.join("s2", "bob", "/repo")          # 1 note
    before = len(engine.messages)
    engine.join("s2", "bob", "/repo")          # active re-join, guarded
    assert len(engine.messages) == before


def test_no_broadcast_when_other_is_stale(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    engine.join("s1", "alice", "/repo")
    clock.t += config.HEARTBEAT_STALE_SECONDS + 1   # s1 now stale
    out2 = engine.join("s2", "bob", "/repo")
    assert out2["colocated"] == {}             # no LIVE other member
    assert len(engine.messages) == 0


def test_offline_rejoin_rebroadcasts(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    engine.join("s1", "alice", "/repo")
    engine.join("s2", "bob", "/repo")          # 1 note from bob
    engine.presence["s2"].status = "offline"   # simulate s2 went offline
    before = len(engine.messages)
    out = engine.join("s2", "bob", "/repo")    # offline -> re-broadcast
    assert out["colocated"] == {"repo-r1": ["alice"]}
    assert len(engine.messages) == before + 1


def test_heartbeat_no_presence(engine, clock):
    assert engine.heartbeat("ghost") == {"ok": False, "need_join": True}


def test_heartbeat_refreshes_and_revives(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    engine.join("s1", "alice", "/repo")
    engine.presence["s1"].status = "offline"
    clock.t += 200
    assert engine.heartbeat("s1") == {"ok": True}
    p = engine.presence["s1"]
    assert p.status == "active"
    assert p.last_heartbeat == clock.t


def test_heartbeat_extends_live_auto_claim_expiry(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    engine.join("s1", "alice", "/repo")
    # auto-claim still live at heartbeat time (expires well in the future)
    auto = Claim(id="clm_auto", board="repo-r1", session_id="s1",
                 label="alice", paths=["/repo/a.py"], kind="auto",
                 created=clock.t, expires=clock.t + 300)
    engine.claims["clm_auto"] = auto
    # explicit claim must NOT be touched by heartbeat
    expl = Claim(id="clm_expl", board="repo-r1", session_id="s1",
                 label="alice", paths=["/repo/b.py"], kind="explicit",
                 created=clock.t, expires=clock.t + 10)
    engine.claims["clm_expl"] = expl
    clock.t += 30
    engine.heartbeat("s1")
    assert (engine.claims["clm_auto"].expires
            == clock.t + config.AUTO_CLAIM_TTL_SECONDS)  # auto extended
    assert engine.claims["clm_expl"].expires == clock.t - 30 + 10  # untouched


def test_leave_marks_offline_and_releases_all_claims(engine, clock, monkeypatch):
    _stub_repo_board(monkeypatch)
    engine.join("s1", "alice", "/repo")
    engine.join("s2", "bob", "/repo")
    auto = Claim(id="clm_a", board="repo-r1", session_id="s1", label="alice",
                 paths=["/repo/a.py"], kind="auto", created=clock.t,
                 expires=clock.t + 300)
    expl = Claim(id="clm_e", board="repo-r1", session_id="s1", label="alice",
                 paths=["/repo/b.py"], kind="explicit", created=clock.t,
                 expires=clock.t + 86400)
    other = Claim(id="clm_o", board="repo-r1", session_id="s2", label="bob",
                  paths=["/repo/c.py"], kind="explicit", created=clock.t,
                  expires=clock.t + 86400)
    for c in (auto, expl, other):
        engine.claims[c.id] = c

    assert engine.leave("s1") == {"ok": True}
    assert engine.presence["s1"].status == "offline"
    assert engine.claims["clm_a"].released is True
    assert engine.claims["clm_e"].released is True
    assert engine.claims["clm_o"].released is False   # other session untouched
    # offline presence persisted
    ppath = os.path.join(engine._board_dir("repo-r1"), "presence", "s1.json")
    assert os.path.exists(ppath)


def test_leave_no_presence_is_ok(engine, clock):
    assert engine.leave("ghost") == {"ok": True}
