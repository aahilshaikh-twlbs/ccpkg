import json

from mailbox.models import Presence, Claim, Message


def test_presence_to_dict_has_all_fields():
    p = Presence(
        session_id="sess-1",
        label="alpha",
        cwd="/repo",
        boards=["repo-abc", "named-foo"],
        joined=100.0,
        last_heartbeat=150.0,
        status="active",
        team="team-1",
        member="m1",
    )
    d = p.to_dict()
    assert d == {
        "session_id": "sess-1",
        "label": "alpha",
        "cwd": "/repo",
        "boards": ["repo-abc", "named-foo"],
        "joined": 100.0,
        "last_heartbeat": 150.0,
        "status": "active",
        "team": "team-1",
        "member": "m1",
    }
    # to_dict must be JSON-serializable
    assert json.loads(json.dumps(d)) == d


def test_presence_round_trip():
    p = Presence(
        session_id="sess-1",
        label="alpha",
        cwd="/repo",
        boards=["repo-abc"],
        joined=100.0,
        last_heartbeat=150.0,
        status="offline",
        team="team-1",
        member="m1",
    )
    assert Presence.from_dict(p.to_dict()) == p


def test_presence_from_dict_tolerates_missing_optionals():
    d = {
        "session_id": "sess-1",
        "label": "alpha",
        "cwd": "/repo",
        "boards": ["repo-abc"],
        "joined": 100.0,
        "last_heartbeat": 150.0,
        "status": "active",
    }
    p = Presence.from_dict(d)
    assert p.team is None
    assert p.member is None
    assert p.boards == ["repo-abc"]


def test_claim_to_dict_has_all_fields():
    c = Claim(
        id="clm_0123456789ab",
        board="repo-abc",
        session_id="sess-1",
        label="alpha",
        paths=["/repo/src/**", "/repo/a.py"],
        kind="explicit",
        created=10.0,
        expires=20.0,
        released=True,
        note="big refactor",
    )
    d = c.to_dict()
    assert d == {
        "id": "clm_0123456789ab",
        "board": "repo-abc",
        "session_id": "sess-1",
        "label": "alpha",
        "paths": ["/repo/src/**", "/repo/a.py"],
        "kind": "explicit",
        "created": 10.0,
        "expires": 20.0,
        "released": True,
        "note": "big refactor",
    }
    assert json.loads(json.dumps(d)) == d


def test_claim_round_trip():
    c = Claim(
        id="clm_0123456789ab",
        board="repo-abc",
        session_id="sess-1",
        label="alpha",
        paths=["/repo/src/**"],
        kind="auto",
        created=10.0,
        expires=20.0,
    )
    assert Claim.from_dict(c.to_dict()) == c


def test_claim_from_dict_tolerates_missing_optionals():
    d = {
        "id": "clm_0123456789ab",
        "board": "repo-abc",
        "session_id": "sess-1",
        "label": "alpha",
        "paths": ["/repo/src/**"],
        "kind": "auto",
        "created": 10.0,
        "expires": 20.0,
    }
    c = Claim.from_dict(d)
    assert c.released is False
    assert c.note is None


def test_message_to_dict_has_all_fields():
    m = Message(
        id="msg_0123456789ab",
        board="repo-abc",
        from_session="sess-1",
        from_label="alpha",
        to="*",
        kind="note",
        body="hello",
        created=5.0,
        read_by=["sess-2"],
        ref_paths=["/repo/a.py"],
    )
    d = m.to_dict()
    assert d == {
        "id": "msg_0123456789ab",
        "board": "repo-abc",
        "from_session": "sess-1",
        "from_label": "alpha",
        "to": "*",
        "kind": "note",
        "body": "hello",
        "created": 5.0,
        "read_by": ["sess-2"],
        "ref_paths": ["/repo/a.py"],
    }
    assert json.loads(json.dumps(d)) == d


def test_message_round_trip():
    m = Message(
        id="msg_0123456789ab",
        board="repo-abc",
        from_session="sess-1",
        from_label="alpha",
        to="beta",
        kind="handoff",
        body="yours now",
        created=5.0,
        read_by=["sess-2"],
        ref_paths=["/repo/a.py"],
    )
    assert Message.from_dict(m.to_dict()) == m


def test_message_from_dict_tolerates_missing_optionals():
    d = {
        "id": "msg_0123456789ab",
        "board": "repo-abc",
        "from_session": "sess-1",
        "from_label": "alpha",
        "to": "*",
        "kind": "note",
        "body": "hello",
        "created": 5.0,
    }
    m = Message.from_dict(d)
    assert m.read_by == []
    assert m.ref_paths == []


def test_message_default_lists_are_independent():
    m1 = Message(
        id="msg_a",
        board="b",
        from_session="s1",
        from_label="l1",
        to="*",
        kind="note",
        body="x",
        created=1.0,
    )
    m2 = Message(
        id="msg_b",
        board="b",
        from_session="s1",
        from_label="l1",
        to="*",
        kind="note",
        body="y",
        created=2.0,
    )
    m1.read_by.append("s2")
    assert m2.read_by == []  # default_factory, not a shared mutable default
