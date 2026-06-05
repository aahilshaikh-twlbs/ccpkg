#!/usr/bin/env python3
"""Nuke mode hook: arm a sticky max-effort directive and re-inject it each turn.

UserPromptSubmit: arm on the <<NUKE-ARM>> sentinel (or a literal /nuke), then
inject the directive on every turn while the per-session flag exists.
SessionEnd: clear the session's flag.

Fail-open ALWAYS: any error exits 0, injects nothing, blocks nothing.
"""
import json
import os
import re
import sys

SENTINEL = "<<NUKE-ARM>>"
_ARM_RE = re.compile(r"(^|\s)/nuke(\s|$)")

DIRECTIVE = (
    "<system-reminder>\n"
    "\U0001f534 NUKE MODE ACTIVE — every remaining turn this session:\n"
    "- ultracode ON — author and run Workflows by default for substantive "
    "work; token cost is not a constraint.\n"
    "- ultrathink — reason as deeply as the task warrants before acting.\n"
    "- ultraplan — plan first, exhaustively, before executing.\n"
    "- Execution model — Workflow orchestrates and runs read-only analysis "
    "fan-out (research/review/audit). All execution/implementation goes to "
    "persistent agent teams (TeamCreate + mailbox SendMessage). Never hand "
    "build work to ephemeral subagents.\n"
    "</system-reminder>"
)


def _state_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "nuke")


def _flag_path(session_id):
    return os.path.join(_state_dir(), session_id + ".flag")


def _emit(text):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": text,
        }
    }
    sys.stdout.write(json.dumps(out))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        session_id = data.get("session_id")
        if not session_id:
            return 0
        flag = _flag_path(session_id)

        prompt = data.get("prompt") or ""
        if SENTINEL in prompt or _ARM_RE.search(prompt):
            os.makedirs(_state_dir(), exist_ok=True)
            with open(flag, "w") as fh:
                fh.write("on")

        if os.path.exists(flag):
            _emit(DIRECTIVE)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
