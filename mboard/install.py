#!/usr/bin/env python3
"""Idempotent installer for Mboard (Contract §14).

Symlinks the repo `bin/mboard` and `hooks/` directory into MBOARD_HOME and merges
the five Mboard hook entries into ~/.claude/settings.json without disturbing any
existing (e.g. notify) hooks. Safe to run repeatedly.
"""
import os
import sys
from typing import List, Optional

# Make the in-repo `src` package importable when run directly from the checkout.
# realpath() so a symlinked install.py still resolves to the real repo; force `src`
# to the FRONT of sys.path (not merely present) so it shadows the stdlib `mboard`
# module even when an editable-install .pth has already appended src further down.
_REPO_ROOT = os.path.dirname(os.path.realpath(__file__))
_SRC = os.path.join(_REPO_ROOT, "src")
if _SRC in sys.path:
    sys.path.remove(_SRC)
sys.path.insert(0, _SRC)

from mboard import config
from mboard import store

# (event_name, matcher_or_None, hook_filename) — Contract §14.
HOOK_SPECS = [
    ("SessionStart", None, "session_start.py"),
    ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit", "pre_tool_use.py"),
    ("PostToolUse", "*", "post_tool_use.py"),
    ("UserPromptSubmit", None, "user_prompt_submit.py"),
    ("SessionEnd", None, "session_end.py"),
    ("Stop", None, "stop.py"),
]


def settings_path() -> str:
    # ~/.claude/settings.json — parent dir of MBOARD_HOME (~/.claude/mboard).
    return os.path.join(os.path.dirname(config.home()), "settings.json")


def _hook_command(home: str, filename: str) -> str:
    # $HOME-relative + quoted so the command is portable across machines/OSes
    # (the shell expands $HOME in Claude Code hook commands). The `home` arg is
    # accepted for signature stability but intentionally not interpolated as an
    # absolute path, so the vendored copy never bakes in a per-user home path.
    # Guarded with `[ -f … ] && … || true` so a transiently-absent hook file
    # (e.g. mid `brew upgrade`, before the symlink is repointed) is a silent
    # no-op instead of a non-zero exit Claude Code reports as a failed/blocking
    # hook. The hooks themselves are fail-open, so forcing exit 0 loses nothing.
    path = '"$HOME/.claude/mboard/hooks/' + filename + '"'
    return "[ -f " + path + " ] && python3 " + path + " || true"


def _event_has_mboard(entries: List[dict]) -> bool:
    for group in entries:
        for h in group.get("hooks", []):
            if "mboard/hooks" in h.get("command", ""):
                return True
    return False


def _replace_symlink(target: str, link_path: str, changes: List[str]) -> None:
    want = os.path.abspath(target)
    if os.path.islink(link_path):
        if os.path.realpath(link_path) == os.path.realpath(want):
            return  # already correct
        os.unlink(link_path)
    elif os.path.exists(link_path):
        # A real file/dir is in the way; remove so we can place the symlink.
        if os.path.isdir(link_path):
            import shutil
            shutil.rmtree(link_path)
        else:
            os.unlink(link_path)
    os.symlink(want, link_path)
    changes.append("symlinked " + link_path + " -> " + want)


def create_symlinks(home: str, repo_root: str) -> List[str]:
    changes = []  # type: List[str]
    os.makedirs(home, exist_ok=True)
    _replace_symlink(os.path.join(repo_root, "bin", "mboard"),
                     os.path.join(home, "mboard"), changes)
    _replace_symlink(os.path.join(repo_root, "hooks"),
                     os.path.join(home, "hooks"), changes)
    return changes


def merge_settings(home: str) -> List[str]:
    changes = []  # type: List[str]
    path = settings_path()
    data = store.read_json(path)  # type: Optional[dict]
    if data is None:
        data = {}
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    for event, matcher, filename in HOOK_SPECS:
        entries = hooks.get(event)
        if not isinstance(entries, list):
            entries = []
            hooks[event] = entries
        if _event_has_mboard(entries):
            continue  # already wired — idempotent skip
        group = {"hooks": [{"type": "command",
                            "command": _hook_command(home, filename)}]}
        if matcher is not None:
            group["matcher"] = matcher
        entries.append(group)
        changes.append("wired " + event + " -> hooks/" + filename)

    if changes:
        store.atomic_write_json(path, data)
    return changes


def main() -> int:
    home = config.home()
    repo_root = os.path.dirname(os.path.abspath(__file__))
    changes = []  # type: List[str]
    changes.extend(create_symlinks(home, repo_root))
    changes.extend(merge_settings(home))
    if changes:
        for c in changes:
            print(c)
    else:
        print("mboard: already installed (no changes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
