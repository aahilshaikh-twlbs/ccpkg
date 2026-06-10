"""Scaffold and wire a private overlay layer (the layer that holds personal /
company content on top of the base).

`init` creates the overlay directory tree (mirroring the base `home/.claude/`
layout) with a starter `manifest.json` + README, then wires the chosen overlay
key (`OVERLAY_DIR` or `OVERLAY_REPO`) into the per-machine `local.env`. It is
idempotent: an existing `dest/manifest.json` is never clobbered, but the
`local.env` wiring is always (re)applied.

Stdlib only, Python 3.9. The `run` callable is injected so tests never execute
real git.
"""
import os
import subprocess
from typing import Callable, Dict, List, Optional

from . import localenv
from . import osenv

# Exact starter manifest body: `{"items": []}` with a trailing newline. Written
# as a literal so it round-trips through json.loads to {"items": []}.
_MANIFEST_BODY = '{\n  "items": []\n}\n'

_README_BODY = (
    "# ccpkg overlay\n"
    "\n"
    "This directory is a **ccpkg overlay**: the private layer that holds your\n"
    "personal or company content on top of the shareable base. It mirrors the\n"
    "base `home/.claude/` layout and declares its own items in `manifest.json`.\n"
    "\n"
    "Every item in this overlay's `manifest.json` MUST use `\"layer\": \"overlay\"`,\n"
    "for example:\n"
    "\n"
    "```json\n"
    "{\n"
    "  \"items\": [\n"
    "    {\"path\": \"agents/my-agent.md\", \"mode\": \"symlink\", \"os\": \"any\", "
    "\"layer\": \"overlay\"}\n"
    "  ]\n"
    "}\n"
    "```\n"
    "\n"
    "ccpkg applies the base first, then this overlay, using the same machinery.\n"
)


def _set_env_key(text, key, value):
    # type: (str, str, str) -> str
    """Return `text` with `KEY=value` set: replace the key's line in place if it
    is already present, else append it. Matches localenv.py's bare `KEY=value`
    format (no quotes). Other lines are preserved verbatim."""
    lines = text.splitlines()
    out = []  # type: List[str]
    replaced = False
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            existing_key = stripped.split("=", 1)[0].strip()
            if existing_key == key:
                out.append("{0}={1}".format(key, value))
                replaced = True
                continue
        out.append(raw)
    if not replaced:
        out.append("{0}={1}".format(key, value))
    return "\n".join(out) + "\n"


def init(dest, localenv_path, repo=None, do_git=False, run=subprocess.run):
    # type: (str, str, Optional[str], bool, Callable) -> Dict[str, object]
    """Scaffold an overlay at `dest` and wire it into the local.env at
    `localenv_path`. Returns a dict of actions taken, e.g.
    {"dest": dest, "created": [...], "localenv": "OVERLAY_DIR=...", "git": bool}.
    Idempotent: if dest already has a manifest.json, do NOT clobber it —
    report 'exists' and still ensure the local.env wiring."""
    created = []  # type: List[str]

    # The overlay mirrors the base layout: home/.claude with an agents/ dir.
    dirs = [
        dest,
        os.path.join(dest, "home", ".claude"),
        os.path.join(dest, "home", ".claude", "agents"),
    ]
    for d in dirs:
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
            created.append(d)

    manifest_file = os.path.join(dest, "manifest.json")
    exists = os.path.exists(manifest_file)
    if not exists:
        with open(manifest_file, "w", encoding="utf-8") as fh:
            fh.write(_MANIFEST_BODY)
        created.append(manifest_file)

    readme_file = os.path.join(dest, "README.md")
    if not os.path.exists(readme_file):
        with open(readme_file, "w", encoding="utf-8") as fh:
            fh.write(_README_BODY)
        created.append(readme_file)

    # Wire local.env: OVERLAY_REPO if a repo was given, else OVERLAY_DIR=<dest>.
    if repo:
        key, value = "OVERLAY_REPO", repo
    else:
        key, value = "OVERLAY_DIR", dest
    existing_text = ""
    if os.path.isfile(localenv_path):
        with open(localenv_path, "r", encoding="utf-8") as fh:
            existing_text = fh.read()
    new_text = _set_env_key(existing_text, key, value)
    parent = os.path.dirname(localenv_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(localenv_path, "w", encoding="utf-8") as fh:
        fh.write(new_text)

    # Optionally `git init` the overlay (only if git is available).
    git_done = False
    if do_git and osenv.have("git"):
        try:
            run(["git", "init", dest], check=False)
            git_done = True
        except Exception:
            git_done = False

    result = {
        "dest": dest,
        "created": created,
        "localenv": "{0}={1}".format(key, value),
        "git": git_done,
    }  # type: Dict[str, object]
    if exists:
        result["exists"] = True
    return result
