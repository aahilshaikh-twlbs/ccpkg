"""Newline-delimited JSON framing + request dispatch (Contract §8)."""

import json


def encode(obj: dict) -> bytes:
    return json.dumps(obj).encode() + b"\n"


def decode(line: bytes) -> dict:
    return json.loads(line)


OPS = {
    "join", "heartbeat", "leave", "check_write", "claim", "release", "seize",
    "request_release", "send", "poll_inbox", "list_claims", "ps", "whoami",
    "board", "gc", "ping",
}


def dispatch(engine, request: dict) -> dict:
    op = request["op"]
    args = request.get("args", {})
    if op == "ping":
        return {"ok": True, "data": "pong"}
    if op not in OPS:
        return {"ok": False, "error": "unknown op: " + str(op)}
    try:
        data = getattr(engine, op)(**args)
        return {"ok": True, "data": data}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
