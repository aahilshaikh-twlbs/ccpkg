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

# Per-op allowlist of client-facing kwargs. Wire args are caller-supplied, so
# anything NOT listed here is stripped before the engine call. This closes a
# privilege gap: release() accepts an internal-only `force` flag that, when
# passed straight through from the wire, let a same-user client drop ANOTHER
# session's claims (selector + force=True). `force` is deliberately absent from
# release's set — it is engine-internal and must never be settable over the
# socket. gc() takes no kwargs.
ALLOWED_ARGS = {
    "join": {"session_id", "label", "cwd", "team", "member", "board_name"},
    "heartbeat": {"session_id"},
    "leave": {"session_id"},
    "check_write": {"session_id", "abs_path"},
    "claim": {"session_id", "globs", "note", "kind"},
    "release": {"session_id", "selector"},          # NOT "force" — internal-only
    "seize": {"session_id", "abs_path"},
    "send": {"session_id", "to", "kind", "body", "ref_paths"},
    "poll_inbox": {"session_id"},
    "request_release": {"session_id", "abs_path"},
    "list_claims": {"session_id", "scope"},
    "ps": {"session_id"},
    "whoami": {"session_id"},
    "board": {"session_id"},
    "gc": set(),
}


def dispatch(engine, request: dict) -> dict:
    op = request["op"]
    args = request.get("args", {})
    if op == "ping":
        return {"ok": True, "data": "pong"}
    if op not in OPS:
        return {"ok": False, "error": "unknown op: " + str(op)}
    # Strip any wire kwarg that is not a legitimate client-facing arg for this op
    # (notably release()'s internal-only `force`).
    allowed = ALLOWED_ARGS.get(op, set())
    if isinstance(args, dict):
        args = {k: v for k, v in args.items() if k in allowed}
    else:
        args = {}
    try:
        data = getattr(engine, op)(**args)
        return {"ok": True, "data": data}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
