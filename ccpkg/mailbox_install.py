"""Wire the vendored mailbox into the live ~/.claude (contract section 11).

Stdlib only. Python 3.9 syntax. Never raises.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from typing import Dict, Optional

from . import config
from . import mergejson

# The 6 mailbox hooks, in (event, matcher, hook-script-basename) form.
# matcher == None means the hook group carries no "matcher" key.
HOOKS = [
    ("UserPromptSubmit", None, "user_prompt_submit.py"),
    ("PostToolUse", "*", "post_tool_use.py"),
    ("SessionStart", None, "session_start.py"),
    ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit", "pre_tool_use.py"),
    ("SessionEnd", None, "session_end.py"),
    ("Stop", None, "stop.py"),
]

_VENDORED_MODULE_NAME = "ccpkg_vendored_mailbox_install"


def mailbox_src(root):
    # type: (str) -> str
    return os.path.join(root, "mailbox")


def _hook_command(script):
    # type: (str) -> str
    # $HOME-relative, quoted so paths with spaces survive shell expansion.
    return 'python3 "$HOME/.claude/mailbox/hooks/%s"' % script


def _ensure_symlink(src_abs, target):
    # type: (str, str) -> None
    parent = os.path.dirname(target)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    if os.path.islink(target):
        # Compare the LITERAL link target, not realpath: a link to a versioned
        # Cellar keg and one to the stable `opt` prefix resolve the same today, but
        # only `opt` survives `brew upgrade`. realpath-equality would skip the
        # Cellar -> opt repoint and leave the link to dangle on the next upgrade.
        if os.readlink(target) == src_abs:
            return
        os.unlink(target)
    elif os.path.exists(target):
        # back up an existing real file/dir, then replace with the symlink
        backup = target + config.backup_suffix()
        if os.path.exists(backup):
            if os.path.isdir(backup) and not os.path.islink(backup):
                shutil.rmtree(backup)
            else:
                os.remove(backup)
        shutil.move(target, backup)
    os.symlink(src_abs, target)


def _hooks_into_settings(existing):
    # type: (Dict) -> Dict
    # Build the mailbox-hooks fragment (de-duplicating any pre-existing mailbox
    # group for our 5 events) and deep-merge it onto `existing` via section 7.
    existing = existing if isinstance(existing, dict) else {}
    prior_hooks = (existing.get("hooks", {}) or {})
    hooks_section = {}
    for evt, _matcher, _script in HOOKS:
        # keep any non-mailbox groups already present for this event
        prior = []
        for grp in (prior_hooks.get(evt, []) or []):
            cmds = [hk.get("command", "") for hk in grp.get("hooks", [])]
            if not any('mailbox/hooks/' in c for c in cmds):
                prior.append(grp)
        hooks_section[evt] = prior

    for evt, matcher, script in HOOKS:
        group = {"hooks": [{"type": "command", "command": _hook_command(script)}]}
        if matcher is not None:
            group["matcher"] = matcher
        hooks_section[evt].append(group)

    # deep_merge the mailbox-hooks fragment onto the existing settings (section 7):
    # scalar/list values for our 5 events are REPLACED by the rebuilt groups,
    # while unrelated events and unrelated top-level keys are preserved.
    return mergejson.deep_merge(existing, {"hooks": hooks_section})


def _builtin_install(root, home_target):
    # type: (str, str) -> Dict[str, str]
    src = mailbox_src(root)
    bin_mailbox = os.path.join(src, "bin", "mailbox")
    hooks_dir = os.path.join(src, "hooks")
    if not os.path.isfile(bin_mailbox) or not os.path.isdir(hooks_dir):
        return {"mailbox": "error", "mode": "builtin",
                "detail": "vendored mailbox source missing at %s" % src}

    _ensure_symlink(bin_mailbox, os.path.join(home_target, "mailbox", "mailbox"))
    _ensure_symlink(hooks_dir, os.path.join(home_target, "mailbox", "hooks"))

    settings_path = os.path.join(home_target, "settings.json")
    existing = {}
    if os.path.isfile(settings_path):
        try:
            with open(settings_path) as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                existing = loaded
        except (ValueError, OSError):
            existing = {}

    new_settings = _hooks_into_settings(existing)
    content = json.dumps(new_settings, indent=2)
    prior_text = None
    if os.path.isfile(settings_path):
        try:
            with open(settings_path) as fh:
                prior_text = fh.read()
        except OSError:
            prior_text = None
    if prior_text is not None and prior_text != content:
        shutil.copyfile(settings_path, settings_path + config.backup_suffix())
    parent = os.path.dirname(settings_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(settings_path, "w") as fh:
        fh.write(content)

    return {"mailbox": "ok", "mode": "builtin"}


def _try_vendored(root, home_target):
    # type: (str, str) -> Optional[Dict[str, str]]
    installer_path = os.path.join(mailbox_src(root), "install.py")
    if not os.path.isfile(installer_path):
        return None
    spec = importlib.util.spec_from_file_location(_VENDORED_MODULE_NAME, installer_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    fn = getattr(module, "install", None)
    if not callable(fn):
        return None
    try:
        fn(home_target)
    except Exception:
        return None
    finally:
        sys.modules.pop(_VENDORED_MODULE_NAME, None)
    return {"mailbox": "ok", "mode": "vendored"}


def install(root, home_target, run=subprocess.run):
    # type: (str, str, object) -> Dict[str, str]
    try:
        vendored = _try_vendored(root, home_target)
        if vendored is not None:
            return vendored
        return _builtin_install(root, home_target)
    except Exception as exc:  # never raises
        return {"mailbox": "error", "detail": str(exc)}
