#!/usr/bin/env python3
"""SessionStart hook: auto-join the mailbox repo board (+ named board). Fail-open."""
import json
import os
import sys

# Add repo src/ to sys.path so `from mailbox import ...` works when run as a
# standalone script (installed/symlinked into ~/.claude/mailbox/hooks).
_REPO_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src"
)
if os.path.isdir(_REPO_SRC) and _REPO_SRC not in sys.path:
    sys.path.insert(0, _REPO_SRC)


def _read_stdin_json():
    data = sys.stdin.read()
    if not data:
        return {}
    return json.loads(data)


def main():
    try:
        from mailbox import client  # import here so sys.path is set first

        payload = _read_stdin_json()
        session_id = payload.get("session_id")
        cwd = payload.get("cwd") or os.getcwd()
        if not session_id:
            return 0

        board_name = os.environ.get("MAILBOX_BOARD") or None
        label = os.environ.get("MAILBOX_LABEL")
        if not label:
            label = os.path.basename(cwd.rstrip("/")) + "-" + session_id[:4]

        resp = client.request(
            "join",
            {
                "session_id": session_id,
                "label": label,
                "cwd": cwd,
                "board_name": board_name,
            },
        )

        data = resp.get("data") if isinstance(resp, dict) else None
        if isinstance(data, dict):
            # The daemon may canonicalize the label; prefer its value.
            label = data.get("label") or label

        env_file = os.environ.get("CLAUDE_ENV_FILE")
        if env_file:
            with open(env_file, "a") as fh:
                fh.write("export MAILBOX_SESSION_ID=" + session_id + "\n")
                fh.write("export MAILBOX_LABEL=" + label + "\n")

        colocated = {}
        if isinstance(data, dict):
            colocated = data.get("colocated") or {}
        if isinstance(colocated, dict):
            for board_id, labels in colocated.items():
                if not labels:
                    continue
                names = ", ".join(labels)
                print(
                    "\U0001f91d Sharing " + str(board_id) + " with: " + names
                    + ". File claims are auto-enforced; use "
                    + "`mailbox ps|claims|send|inbox` to coordinate."
                )

        return 0
    except Exception:
        # Fail-open: never block session start.
        return 0


if __name__ == "__main__":
    sys.exit(main())
