"""iTerm2 osascript automation: spawn_tab, inject, close_panes.

All functions raise ITermError on osascript failure so the caller can degrade
gracefully (e.g. to B-assisted: printing the kickoff prompt for paste).

NOTE: the exact osascript shape (presence registration timing, `id` vs
`id of current session`, write-text chunking) is validated/finalized by the
Probe 2 live smoke in a bypass-mode session (see plan Task 0). The unit tests
here only pin the contract: env + cmd appear in the spawn script, pane ids are
returned/echoed, failures raise ITermError.
"""
import shlex
import subprocess


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


def spawn_tab(env, cmd):
    """Open a new iTerm2 tab, set `env`, run `cmd`. Return the new pane id."""
    exports = " ".join(
        "{}={}".format(k, shlex.quote(str(v))) for k, v in env.items()
    )
    full_cmd = "{} {}".format(exports, cmd).strip()
    script = (
        'tell application "iTerm"\n'
        '  tell current window\n'
        '    set newTab to (create tab with default profile)\n'
        '    tell current session of newTab\n'
        '      write text {}\n'
        '      return id\n'
        '    end tell\n'
        '  end tell\n'
        'end tell\n'
    ).format(_osa_str(full_cmd))
    return _run_osa(script)


def inject(pane_id, text):
    """Write `text` into an existing iTerm2 session (by pane id)."""
    script = (
        'tell application "iTerm"\n'
        '  tell session id {}\n'
        '    write text {}\n'
        '  end tell\n'
        'end tell\n'
    ).format(_osa_str(pane_id), _osa_str(text))
    _run_osa(script)


def close_panes(pane_ids):
    """Close each pane by id. Errors per-pane are surfaced via ITermError."""
    for pid in pane_ids:
        script = (
            'tell application "iTerm"\n'
            '  tell session id {}\n'
            '    close\n'
            '  end tell\n'
            'end tell\n'
        ).format(_osa_str(pid))
        _run_osa(script)
