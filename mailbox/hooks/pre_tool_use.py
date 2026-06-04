#!/usr/bin/env python3
"""PreToolUse hook: anti-collision check for write tools (fail-open)."""
import json
import os
import sys

# Bootstrap: add repo src to sys.path so `import mailbox` works whether this
# file is run from the repo or via the installed symlink in ~/.claude/mailbox.
_HOOK_DIR = os.path.dirname(os.path.realpath(__file__))
_SRC = os.path.join(os.path.dirname(_HOOK_DIR), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def main():
    try:
        raw = sys.stdin.read()
        data_in = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    try:
        from mailbox import client, config

        session_id = data_in.get("session_id")
        cwd = data_in.get("cwd") or os.getcwd()
        tool_name = data_in.get("tool_name")
        tool_input = data_in.get("tool_input") or {}

        if tool_name not in config.WRITE_TOOLS:
            return 0

        fp = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not fp:
            return 0

        abs_path = os.path.abspath(os.path.join(cwd, fp))

        resp = client.request("check_write", {
            "session_id": session_id,
            "abs_path": abs_path,
        })
        if not resp.get("ok"):
            return 0
        result = resp.get("data") or {}
        decision = result.get("decision")

        if decision == "deny":
            holder = result.get("holder")
            since = int(round(result.get("since_seconds") or 0))
            note = result.get("note")
            note_part = "; " + note if note else ""
            reason = (
                "\U0001f512 " + str(holder) + " holds " + abs_path
                + " (active " + str(since) + "s ago)" + note_part
                + ". Coordinate: `mailbox request-release " + abs_path
                + "` or work elsewhere."
            )
            out = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
            sys.stdout.write(json.dumps(out))
            return 0

        if decision == "warn":
            holder = result.get("holder")
            stale = int(round(result.get("stale_seconds") or 0))
            context = (
                "⚠️ " + str(holder) + " has a STALE claim on "
                + abs_path + " (" + str(stale) + "s). Proceeding, but if "
                "they're still working this will collide. `mailbox seize "
                + abs_path + "` to take ownership."
            )
            out = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "additionalContext": context,
                }
            }
            sys.stdout.write(json.dumps(out))
            return 0

        # "allow" or anything else: no output; auto-claim recorded by daemon.
        return 0
    except Exception:
        # Fail-open: never block real work on a mailbox error.
        return 0


if __name__ == "__main__":
    sys.exit(main())
