"""Shareable setups (ccpkg.share.json): export the current selection to a
portable, base-pure artifact, and resolve a shared source (git repo URL or a
local path) back to a selected-id set for `apply`. Stdlib only, Python 3.9.

A "setup" is just the SELECTION of catalog ids (agents / packs / skills /
plugins / mboard / ...). It carries no secrets and no files, so the artifact is
always safe to publish. The recipient applies it against the same public base,
reconstructing your picks; ids their catalog doesn't have are skipped.
"""

import json
import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Set, Tuple

from . import config
from . import manifest
from . import profile
from . import selectables
from . import selection
from . import __version__

SHARE_FILENAME = "ccpkg.share.json"
SHARE_SCHEMA = 1
PRESETS = ("minimal", "recommended", "everything")


def is_preset(source):
    # type: (str) -> bool
    return source in PRESETS


def _catalog(root, overlay_present):
    # type: (str, bool) -> Dict[str, Tuple[str, str]]
    """id -> (group, desc) for every surfaced installable (files + selectables),
    using the same staging the wizard/profile use as the source of truth."""
    items = manifest.parse(config.manifest_path(root))
    cat = {}
    for stage in selection.build_stages(items, selectables.SELECTABLES,
                                        overlay_present):
        for e in stage.entries:
            cat[e.id] = (stage.name, getattr(e, "desc", ""))
    return cat


def export_setup(root, home, overlay_present=False):
    # type: (str, str, bool) -> dict
    """Build the shareable artifact from the saved profile, or the default-on
    set when no profile exists. Pure data — ids + human-readable labels only."""
    cat = _catalog(root, overlay_present)
    prof = profile.load(home)
    if prof is not None:
        selected = list(prof.selected)
        deselected = list(prof.deselected)
    else:
        items = manifest.parse(config.manifest_path(root))
        selected = sorted(selection.default_ids(items, selectables.SELECTABLES,
                                                 overlay_present))
        deselected = []
    items_list = [{"id": sid,
                   "group": cat.get(sid, ("", ""))[0],
                   "desc": cat.get(sid, ("", ""))[1]}
                  for sid in selected]
    return {
        "ccpkg_share": SHARE_SCHEMA,
        "ccpkg_version": __version__,
        "selected": selected,
        "deselected": deselected,
        "items": items_list,
    }


def write_share(data, out_path):
    # type: (dict, str) -> str
    """Atomically write the artifact (tmp + os.replace). Returns the path."""
    parent = os.path.dirname(out_path) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, out_path)
    return out_path


def _looks_like_repo(source):
    # type: (str) -> bool
    return (source.startswith(("http://", "https://", "git@", "ssh://"))
            or source.endswith(".git"))


def _read_share(path):
    # type: (str) -> dict
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read {0}: {1}".format(path, exc))
    if (not isinstance(data, dict) or "ccpkg_share" not in data
            or not isinstance(data.get("selected"), list)):
        raise ValueError("{0} is not a valid ccpkg share file".format(path))
    return data


def fetch_share(source, run=subprocess.run):
    # type: (str, object) -> dict
    """Resolve a non-preset source to a parsed share dict. `source` is a git
    repo URL (shallow-cloned to a temp dir) or a local path (the file itself, or
    a directory containing ccpkg.share.json). Raises ValueError if it can't be
    resolved to a valid share file."""
    if _looks_like_repo(source):
        tmp = tempfile.mkdtemp(prefix="ccpkg-share-")
        try:
            run(["git", "clone", "--depth", "1", source, tmp], check=False)
            path = os.path.join(tmp, SHARE_FILENAME)
            if not os.path.isfile(path):
                raise ValueError(
                    "no {0} at the root of {1}".format(SHARE_FILENAME, source))
            return _read_share(path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    path = source
    if os.path.isdir(path):
        path = os.path.join(path, SHARE_FILENAME)
    if not os.path.isfile(path):
        raise ValueError(
            "not a preset, git URL, or path to {0}: {1}".format(
                SHARE_FILENAME, source))
    return _read_share(path)


def resolve_selection(data, root, overlay_present=False):
    # type: (dict, str, bool) -> Tuple[Set[str], List[dict], List[str]]
    """Intersect the shared selection with THIS machine's catalog. Returns
    (selected_ids, preview_items, skipped_ids); unknown ids are skipped so a
    share from a different catalog version still applies what it can."""
    cat = _catalog(root, overlay_present)
    shared = [str(x) for x in data.get("selected", [])]
    resolved = set()
    skipped = []
    preview = []
    for sid in shared:
        if sid in cat:
            resolved.add(sid)
            preview.append({"id": sid, "group": cat[sid][0], "desc": cat[sid][1]})
        else:
            skipped.append(sid)
    return resolved, preview, skipped


def catalog_ids(root, overlay_present=False):
    # type: (str, bool) -> Set[str]
    """Every installable id this machine's catalog surfaces (for computing the
    `deselected` complement when adopting a shared setup)."""
    return set(_catalog(root, overlay_present).keys())
