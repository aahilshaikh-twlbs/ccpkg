#!/usr/bin/env python3
"""SessionEnd hook: mark this session offline and release its claims.

Contract §13: read session_id from stdin JSON; call leave; exit 0.
Fail-open ALWAYS — any internal error exits 0 silently and never blocks work.
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
        from mailbox import client
        client.request("leave", {"session_id": sid})
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
