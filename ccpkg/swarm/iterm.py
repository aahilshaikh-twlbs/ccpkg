"""iTerm2 osascript automation: spawn_tab, inject, close_panes.

All functions raise ITermError on osascript failure so the caller can degrade
gracefully (e.g. to B-assisted: printing the kickoff prompt for paste).

The osascript shapes here were validated by the Task 0 / Probe 2 live smoke in a
bypass-mode session (see docs/superpowers/plans/feasibility-gate-result.md):

- A launched tab inherits the *active* session's cwd, not the orchestrator's, so
  `spawn_tab` cd's into the target repo before launching.
- `tell session id "<uuid>"` does NOT resolve in iTerm (-1728); sessions must be
  located by iterating windows/tabs/sessions and matching `id of s`.
- `write text "<prompt>"` lands the text in the TUI input but the auto-newline is
  swallowed by bracketed-paste handling, so it never submits; `inject` types the
  text with `newline no` then sends a separate bare return to submit.
"""
import shlex
import subprocess

# Seconds to let a freshly-created tab's login shell finish starting up before
# typing the launch command into it. Writing immediately races shell init and
# garbles the command (Task 8 smoke: `cd` arrived as `acd`).
SPAWN_SETTLE_DELAY = 2.0


class ITermError(Exception):
    pass


def _osa_str(value):
    """Quote a Python string as an AppleScript string literal."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run_osa(script):
    result = subprocess.run(
        ["osascript", "-"],
        input=script,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ITermError(result.stderr.strip() or "osascript failed")
    return result.stdout.strip()


def _tell_session_by_id(pane_id, body_lines):
    """AppleScript that finds a session by its `id` (FORM B) and runs body inside
    `tell s`. `tell session id "X"` is broken in iTerm, so we iterate instead."""
    return (
        'tell application "iTerm"\n'
        '  repeat with w in windows\n'
        '    repeat with t in tabs of w\n'
        '      repeat with s in sessions of t\n'
        '        if (id of s) is {} then\n'
        '          tell s\n'
        '{}'
        '          end tell\n'
        '          return\n'
        '        end if\n'
        '      end repeat\n'
        '    end repeat\n'
        '  end repeat\n'
        'end tell\n'
    ).format(_osa_str(pane_id), body_lines)


def spawn_tab(env, cmd, cwd=None):
    """Open a new iTerm2 tab, cd into `cwd`, set `env`, run `cmd`. Return pane id.

    `cwd` matters: a new tab inherits the active session's working directory, not
    the orchestrator's, so leads would otherwise launch in the wrong repo.
    """
    exports = " ".join(
        "{}={}".format(k, shlex.quote(str(v))) for k, v in env.items()
    )
    launch = "{} {}".format(exports, cmd).strip()
    if cwd:
        full_cmd = "cd {} && {}".format(shlex.quote(str(cwd)), launch)
    else:
        full_cmd = launch
    script = (
        'tell application "iTerm"\n'
        '  tell current window\n'
        '    set newTab to (create tab with default profile)\n'
        '    tell current session of newTab\n'
        '      delay {}\n'
        '      write text {}\n'
        '      return id\n'
        '    end tell\n'
        '  end tell\n'
        'end tell\n'
    ).format(SPAWN_SETTLE_DELAY, _osa_str(full_cmd))
    return _run_osa(script)


def inject(pane_id, text):
    """Write `text` into an existing iTerm2 session (by pane id) and submit it.

    Types the text without a trailing newline (the auto-newline is swallowed),
    then sends a separate bare return so the REPL actually submits the prompt.
    """
    body = (
        '            write text {} newline no\n'
        '            delay 1\n'
        '            write text ""\n'
    ).format(_osa_str(text))
    _run_osa(_tell_session_by_id(pane_id, body))


def close_panes(pane_ids):
    """Close each pane by id. Errors per-pane are surfaced via ITermError."""
    for pid in pane_ids:
        _run_osa(_tell_session_by_id(pid, "            close\n"))
