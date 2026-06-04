#!/usr/bin/env python3
"""UserPromptSubmit hook: heartbeat + poll inbox, inject unread messages.

Fail-open ALWAYS: any exception -> exit 0 with no output (never block work).
Contract §13.
"""
import json
import os
import sys

# Make `mailbox` importable whether run from the dev repo or the installed
# symlink layout (hooks/ sits next to src/ in the repo).
_REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src")
if os.path.isdir(_REPO_SRC) and _REPO_SRC not in sys.path:
    sys.path.insert(0, _REPO_SRC)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        session_id = data.get("session_id")
        if not session_id:
            return 0
        from mailbox import client

        client.request("heartbeat", {"session_id": session_id})
        resp = client.request("poll_inbox", {"session_id": session_id})
        if not resp or not resp.get("ok"):
            return 0
        messages = resp.get("data") or []
        if not messages:
            return 0
        lines = ["📬 Mailbox:"]
        for m in messages:
            lines.append(
                "[%s] from %s: %s"
                % (m.get("kind", ""), m.get("from_label", ""), m.get("body", ""))
            )
        text = "\n".join(lines)
        out = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": text,
            }
        }
        sys.stdout.write(json.dumps(out))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
