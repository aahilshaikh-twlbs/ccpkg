"""Reverse a ccpkg install: remove the managed files it laid into ~/.claude,
restoring the pre-install `*.ccpkg.bak` backups where present, then drop the
mboard runtime and the saved profile. Stdlib only, Python 3.9.

Safety: merge-mode files (settings.json) are NEVER deleted outright — they may
hold the user's own keys. We restore the backup if one exists, otherwise leave
the file in place and report it for manual review. Symlinks we created and
rendered template outputs are removed (backup restored first if present).
"""
import os
import shutil
from typing import List, Tuple

from . import config, manifest, profile


def _target_for(item, home):
    # type: (manifest.Item, str) -> str
    target = os.path.join(home, item.path)
    if item.mode == "template" and target.endswith(".tmpl"):
        target = target[: -len(".tmpl")]
    return target


def base_targets(root, home, os_name):
    # type: (str, str, str) -> List[Tuple[object, str]]
    """(item, target_abs) for every base item that applies to this OS — the set
    uninstall would touch. Used for the pre-confirm preview."""
    items = manifest.parse(config.manifest_path(root))
    out = []  # type: List[Tuple[object, str]]
    for item in items:
        if item.layer != "base":
            continue
        if not manifest.applies_to_os(item, os_name):
            continue
        out.append((item, _target_for(item, home)))
    return out


def plan(root, home, os_name):
    # type: (str, str, str) -> List[str]
    """Human-readable target paths uninstall would touch (for the confirm prompt)."""
    return [t for _it, t in base_targets(root, home, os_name)]


def _remove_one(item, target):
    # type: (object, str) -> str
    backup = target + config.backup_suffix()
    have_backup = os.path.isfile(backup)

    if item.mode == "merge":
        # Never delete a merge target outright; restore the backup or leave it.
        if have_backup:
            os.replace(backup, target)
            return "restored-backup"
        if os.path.exists(target):
            return "left (no backup — review manually)"
        return "absent"

    # symlink / template
    if os.path.islink(target):
        os.remove(target)
        if have_backup:
            os.replace(backup, target)
            return "removed-symlink + restored-backup"
        return "removed-symlink"
    if os.path.isfile(target):
        if have_backup:
            os.replace(backup, target)
            return "restored-backup"
        os.remove(target)
        return "removed-file"
    # Target gone already; tidy a stray backup if one lingers.
    if have_backup:
        os.replace(backup, target)
        return "restored-backup"
    return "absent"


def uninstall(root, home, os_name, remove_mboard=True):
    # type: (str, str, str, bool) -> List[Tuple[str, str]]
    """Perform the uninstall. Returns (label, status) for every action."""
    results = []  # type: List[Tuple[str, str]]
    for item, target in base_targets(root, home, os_name):
        results.append((item.path, _remove_one(item, target)))

    if remove_mboard:
        mb_dir = os.path.join(home, "mboard")
        if os.path.isdir(mb_dir) or os.path.islink(mb_dir):
            shutil.rmtree(mb_dir, ignore_errors=True)
            results.append(("mboard", "removed"))
        else:
            results.append(("mboard", "absent"))

    prof_path = os.path.join(home, profile.PROFILE_NAME)
    if os.path.isfile(prof_path):
        os.remove(prof_path)
        results.append((profile.PROFILE_NAME, "removed"))
    else:
        results.append((profile.PROFILE_NAME, "absent"))

    return results
