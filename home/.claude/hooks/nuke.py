#!/usr/bin/env python3
"""Nuke mode hook (UserPromptSubmit): toggle ultracode + inject the team directive.

  /nuke   or  /nuke arm       -> set "ultracode": true in settings.local.json
  /nuke off  or  /nuke disarm -> remove "ultracode" from settings.local.json

`ultracode` (xhigh effort + dynamic workflows) is a launch-time setting, so a
toggle applies from the NEXT session; for the current session the user runs
`/effort ultracode`. While armed, a standing directive is injected each turn
preferring persistent agent teams (TeamCreate + mboard) over ephemeral
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
    "and `permissions.defaultMode = bypassPermissions` are now set in your "
    "settings, ACTIVE from your next session. For THIS session, run "
    "`/effort ultracode` to apply ultracode now; bypass mode requires a "
    "session relaunch (e.g. `claude --dangerously-skip-permissions`). "
    "Execution preference: use persistent agent teams (TeamCreate + mboard) "
    "over ephemeral subagents.\n"
    "</system-reminder>"
)
DISARMED_MSG = (
    "<system-reminder>\n"
    "⚪ NUKE MODE DISARMED — ultracode removed and prior "
    "`permissions.defaultMode` restored in settings; off from your next "
    "session. Run `/effort auto` to lower this session now.\n"
    "</system-reminder>"
)
ALREADY_OFF_MSG = (
    "<system-reminder>\n"
    "⚪ NUKE MODE already off — `ultracode` was not set in settings, so "
    "nothing changed. If the statusline still shows \U0001f534 NUKE, that is "
    "THIS session's effort (CLAUDE_EFFORT=xhigh), not the persistent toggle; "
    "run `/effort auto` to lower it now.\n"
    "</system-reminder>"
)
ALREADY_ARMED_MSG = (
    "<system-reminder>\n"
    "\U0001f534 NUKE MODE already armed — `ultracode` is already set; nothing "
    "changed. Active from your next session. For THIS session run "
    "`/effort ultracode` if it is not already at xhigh.\n"
    "</system-reminder>"
)
STANDING_MSG = (
    "<system-reminder>\n"
    "\U0001f534 NUKE MODE active — ultracode on (xhigh + dynamic workflows). "
    "Prefer persistent agent teams (TeamCreate + mboard) over ephemeral "
    "subagents for implementation work. For substantive multi-aspect tasks "
    "(refactors, audits, builds with >2 distinct concerns), call `/swarm "
    "<task>` BEFORE writing code — it fans out across federated Claude leads "
    "in iTerm2 tabs.\n"
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


NUKE_PERM_MODE = "bypassPermissions"


def _sidecar_path():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "nuke", "prior.json")


def _sidecar_load():
    try:
        with open(_sidecar_path()) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _sidecar_write(prior_default_mode):
    path = _sidecar_path()
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w") as fh:
        json.dump({"defaultMode": prior_default_mode}, fh)


def _sidecar_clear():
    try:
        os.remove(_sidecar_path())
    except OSError:
        pass


def _arm():
    data = _load()
    perms = data.get("permissions")
    if not isinstance(perms, dict):
        perms = {}
    prior = perms.get("defaultMode")
    # Idempotent re-arm: only record a prior if we're NOT already armed AND
    # no sidecar already exists (preserves the original prior across re-arm).
    if prior != NUKE_PERM_MODE and _sidecar_load() is None:
        _sidecar_write(prior)
    perms["defaultMode"] = NUKE_PERM_MODE
    data["permissions"] = perms
    data["ultracode"] = True
    _write(data)


def _disarm():
    data = _load()
    data.pop("ultracode", None)
    sidecar = _sidecar_load()
    if sidecar is not None:
        perms = data.get("permissions")
        if isinstance(perms, dict):
            prior = sidecar.get("defaultMode")
            if prior is None:
                perms.pop("defaultMode", None)
                if not perms:
                    data.pop("permissions", None)
            else:
                perms["defaultMode"] = prior
                data["permissions"] = perms
        _sidecar_clear()
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
            if _is_armed():
                _emit(ALREADY_ARMED_MSG)
            else:
                _arm()
                _emit(ARMED_MSG)
        elif intent == "disarm":
            # "Off" means nothing to undo: not armed AND no stashed perms to
            # restore. Report it rather than claiming a disarm that did nothing.
            if _is_armed() or _sidecar_load() is not None:
                _disarm()
                _emit(DISARMED_MSG)
            else:
                _emit(ALREADY_OFF_MSG)
        elif _is_armed():
            _emit(STANDING_MSG)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
