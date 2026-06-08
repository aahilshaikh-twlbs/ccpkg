#!/usr/bin/env python3
"""Nuke mode hook (UserPromptSubmit): toggle ultracode + inject the team directive.

  /nuke   or  /nuke arm       -> set "ultracode": true in settings.local.json
  /nuke off  or  /nuke disarm -> remove "ultracode" from settings.local.json

`ultracode` (xhigh effort + dynamic workflows) is a launch-time setting, so a
toggle applies from the NEXT session; for the current session the user runs
`/effort ultracode`. While armed, a standing directive is injected each turn
preferring persistent agent teams (TeamCreate + mailbox) over ephemeral
subagents — the one half of "nuke" that has no native switch.

Fail-open ALWAYS: any error exits 0, changes nothing, blocks nothing.
"""
import json
import os
import re
import sys

# Intent detection. The /nuke command body expands to "<<NUKE:$ARGUMENTS>>", so
# the hook sees the sentinel when commands are expanded, or the raw "/nuke ..."
# otherwise. Either carries the (optional) arg word in group(1).
_SENTINEL_RE = re.compile(r"<<NUKE:([^>]*)>>")
_CMD_RE = re.compile(r"(?:^|\s)/nuke(?:\s+(\w+))?", re.IGNORECASE)
_DISARM_WORDS = {"off", "disarm", "stop"}

ARMED_MSG = (
    "<system-reminder>\n"
    "\U0001f534 NUKE MODE ARMED — ultracode (xhigh effort + dynamic workflows) "
    "is now set in your settings and will be ACTIVE from your next session. For "
    "THIS session, run `/effort ultracode` to apply it now. Execution "
    "preference: use persistent agent teams (TeamCreate + mailbox) over "
    "ephemeral subagents for implementation work.\n"
    "</system-reminder>"
)
DISARMED_MSG = (
    "<system-reminder>\n"
    "⚪ NUKE MODE DISARMED — ultracode removed from settings; off from your "
    "next session. Run `/effort auto` to lower this session now.\n"
    "</system-reminder>"
)
STANDING_MSG = (
    "<system-reminder>\n"
    "\U0001f534 NUKE MODE active — ultracode on (xhigh + dynamic workflows). "
    "Prefer persistent agent teams (TeamCreate + mailbox) over ephemeral "
    "subagents for implementation work.\n"
    "</system-reminder>"
)


def _settings_path():
    # User-level settings.json is the only file the harness honors for the
    # `ultracode` setting (settings.local.json is NOT read for effort). Verified
    # live: settings.json {"ultracode": true} -> xhigh + dynamic workflows.
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "settings.json")


def _load():
    try:
        with open(_settings_path()) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(data):
    path = _settings_path()
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


def _set_ultracode(on):
    data = _load()
    if on:
        data["ultracode"] = True
    else:
        data.pop("ultracode", None)
    _write(data)


def _is_armed():
    return _load().get("ultracode") is True


def _intent(prompt):
    """Return 'arm', 'disarm', or None for the given prompt."""
    m = _SENTINEL_RE.search(prompt) or _CMD_RE.search(prompt)
    if m is None:
        return None
    arg = (m.group(1) or "").strip().lower()
    return "disarm" if arg in _DISARM_WORDS else "arm"


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
        prompt = data.get("prompt") or ""
        intent = _intent(prompt)
        if intent == "arm":
            _set_ultracode(True)
            _emit(ARMED_MSG)
        elif intent == "disarm":
            _set_ultracode(False)
            _emit(DISARMED_MSG)
        elif _is_armed():
            _emit(STANDING_MSG)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
