import json

import pytest

from mboard import protocol


def test_encode_appends_newline_and_is_json():
    obj = {"op": "ping", "args": {}}
    out = protocol.encode(obj)
    assert isinstance(out, bytes)
    assert out.endswith(b"\n")
    assert json.loads(out.decode()) == obj


def test_decode_parses_bytes_line():
    line = b'{"ok": true, "data": "pong"}\n'
    got = protocol.decode(line)
    assert got == {"ok": True, "data": "pong"}


def test_encode_decode_round_trip():
    obj = {"op": "join", "args": {"session_id": "s1", "label": "alpha"}}
    assert protocol.decode(protocol.encode(obj)) == obj


def test_dispatch_ping_returns_pong():
    resp = protocol.dispatch(None, {"op": "ping"})
    assert resp == {"ok": True, "data": "pong"}


def test_dispatch_unknown_op_returns_error():
    resp = protocol.dispatch(None, {"op": "frobnicate", "args": {}})
    assert resp["ok"] is False
    assert resp["error"] == "unknown op: frobnicate"


def test_dispatch_join_returns_ok_and_data(engine):
    resp = protocol.dispatch(
        engine,
        {"op": "join", "args": {"session_id": "s1", "label": "alpha", "cwd": "/tmp/repo"}},
    )
    assert resp["ok"] is True
    data = resp["data"]
    assert data["label"] == "alpha"
    assert isinstance(data["boards"], list) and len(data["boards"]) >= 1
    assert "colocated" in data


def test_dispatch_release_strips_force_cannot_drop_other_session_claim(engine):
    # F3: `force` is an engine-internal kwarg. A same-user client must not be able
    # to send force=True over the wire to drop a claim owned by ANOTHER session.
    protocol.dispatch(engine, {"op": "join",
        "args": {"session_id": "s1", "label": "alpha", "cwd": "/tmp/repo"}})
    claimed = protocol.dispatch(engine, {"op": "claim",
        "args": {"session_id": "s1", "globs": ["src/x.py"]}})
    claim_id = claimed["data"]["id"]

    # s2 (a different session) attempts a forced release of s1's claim.
    resp = protocol.dispatch(engine, {"op": "release",
        "args": {"session_id": "s2", "selector": claim_id, "force": True}})
    assert resp["ok"] is True
    assert resp["data"]["released"] == []              # force stripped: nothing released
    assert engine.claims[claim_id].released is False   # s1's claim survives


def test_dispatch_release_owner_release_still_works(engine):
    # Regression: stripping `force` must not break a legitimate owner release.
    protocol.dispatch(engine, {"op": "join",
        "args": {"session_id": "s1", "label": "alpha", "cwd": "/tmp/repo"}})
    claimed = protocol.dispatch(engine, {"op": "claim",
        "args": {"session_id": "s1", "globs": ["src/x.py"]}})
    claim_id = claimed["data"]["id"]
    resp = protocol.dispatch(engine, {"op": "release",
        "args": {"session_id": "s1", "selector": claim_id}})
    assert resp["data"]["released"] == [claim_id]
    assert engine.claims[claim_id].released is True


def test_dispatch_exception_captured_not_raised(engine):
    # check_write requires (session_id, abs_path); omitting abs_path raises
    # TypeError inside the engine call, which dispatch must capture into the
    # error field rather than propagate.
    resp = protocol.dispatch(engine, {"op": "check_write", "args": {"session_id": "s1"}})
    assert resp["ok"] is False
    assert resp["error"].startswith("TypeError")
