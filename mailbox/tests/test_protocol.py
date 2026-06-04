import json

import pytest

from mailbox import protocol


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


def test_dispatch_exception_captured_not_raised(engine):
    # check_write requires (session_id, abs_path); omitting abs_path raises
    # TypeError inside the engine call, which dispatch must capture into the
    # error field rather than propagate.
    resp = protocol.dispatch(engine, {"op": "check_write", "args": {"session_id": "s1"}})
    assert resp["ok"] is False
    assert resp["error"].startswith("TypeError")
