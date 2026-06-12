#!/usr/bin/env python3
"""Stop hook: release this session's AUTO claims at turn end (presence stays active).

Turn-end release: a session holds auto-claims only while actively editing within a
turn. When the turn ends, free them so other sessions/teams working the same dir can
claim those files. Explicit claims and presence are left intact (unlike SessionEnd's
`leave`, which goes offline and drops everything).

Fail-open ALWAYS: any error exits 0 silently and never blocks work.
"""
import json
import os
import sys

# Make the repo's src/ importable when running uninstalled (Contract §13).
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    try:
        sid = payload.get("session_id")
        if not sid:
            return 0
        from mboard import client
        client.request("release", {"session_id": sid, "selector": "auto"})
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
