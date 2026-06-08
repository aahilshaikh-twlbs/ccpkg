"""Filesystem layout for swarm runs.

Root: $CCPKG_SWARM_ROOT or /tmp/ccpkg-swarm

Layout:
    <root>/<swarm_id>/meta.json
    <root>/<swarm_id>/<lead>/inbox.md
    <root>/<swarm_id>/<lead>/result.md   (lead writes)
"""
import json
import os
import secrets
import time


def _root_dir():
    return os.environ.get("CCPKG_SWARM_ROOT") or "/tmp/ccpkg-swarm"


def mint_swarm_id():
    return secrets.token_hex(4)


def root(swarm_id):
    return os.path.join(_root_dir(), swarm_id)


def lead_dir(swarm_id, lead):
    return os.path.join(root(swarm_id), lead)


def inbox_path(swarm_id, lead):
    return os.path.join(lead_dir(swarm_id, lead), "inbox.md")


def result_path(swarm_id, lead):
    return os.path.join(lead_dir(swarm_id, lead), "result.md")


def meta_path(swarm_id):
    return os.path.join(root(swarm_id), "meta.json")


def setup(swarm_id, leads, task, inboxes):
    """Create the workdir tree + initial meta.json. Idempotent."""
    os.makedirs(root(swarm_id), exist_ok=True)
    for lead in leads:
        os.makedirs(lead_dir(swarm_id, lead), exist_ok=True)
        with open(inbox_path(swarm_id, lead), "w") as fh:
            fh.write(inboxes[lead])
    meta = {
        "swarm_id": swarm_id,
        "leads": list(leads),
        "task": task,
        "created_at": int(time.time()),
        "pane_ids": {},
    }
    with open(meta_path(swarm_id), "w") as fh:
        json.dump(meta, fh, indent=2)


def record_pane_ids(swarm_id, pane_ids):
    """Persist pane_ids for later /swarm close."""
    path = meta_path(swarm_id)
    with open(path) as fh:
        meta = json.load(fh)
    meta["pane_ids"] = dict(pane_ids)
    with open(path, "w") as fh:
        json.dump(meta, fh, indent=2)


def list_swarms():
    """Return active swarms as a list of meta dicts."""
    rootdir = _root_dir()
    if not os.path.isdir(rootdir):
        return []
    out = []
    for name in os.listdir(rootdir):
        mp = os.path.join(rootdir, name, "meta.json")
        if os.path.isfile(mp):
            try:
                with open(mp) as fh:
                    out.append(json.load(fh))
            except (OSError, ValueError):
                continue
    return out
