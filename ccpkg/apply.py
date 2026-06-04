"""Lay managed files down: symlink / template / merge (Contract section 9).

Idempotent and safe: existing real files are backed up before overwrite. stdlib
only, Python 3.9 syntax. Depends on sibling ccpkg modules config/manifest/
mergejson/template.
"""
import json
import os
import shutil
from typing import Dict, List, Optional, Tuple

from . import config, manifest, mergejson, template


def backup_then_write(target, content):
    # type: (str, str) -> Optional[str]
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    backup = None
    if os.path.isfile(target) and not os.path.islink(target):
        with open(target) as fh:
            existing = fh.read()
        if existing != content:
            backup = target + config.backup_suffix()
            shutil.copyfile(target, backup)
    elif os.path.islink(target):
        backup = target + config.backup_suffix()
        shutil.copyfile(target, backup)
        os.remove(target)
    with open(target, "w") as fh:
        fh.write(content)
    return backup


def apply_symlink(src_abs, target):
    # type: (str, str) -> str
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.islink(target):
        if os.path.realpath(target) == os.path.realpath(src_abs):
            return "ok"
        os.remove(target)
    elif os.path.exists(target):
        shutil.copyfile(target, target + config.backup_suffix())
        os.remove(target)
    os.symlink(src_abs, target)
    return "linked"


def apply_template(src_tmpl_path, target, vars, vault_enabled):
    # type: (str, str, Dict[str, str], bool) -> str
    if target.endswith(".tmpl"):
        target = target[: -len(".tmpl")]
    with open(src_tmpl_path) as fh:
        raw = fh.read()
    rendered = template.render(raw, vars, vault_enabled)
    backup_then_write(target, rendered)
    return "rendered"


def apply_merge_json(src_json_path, target):
    # type: (str, str) -> str
    with open(src_json_path) as fh:
        base_obj = json.load(fh)
    merged = mergejson.merge_settings_file(target, base_obj)
    backup_then_write(target, json.dumps(merged, indent=2))
    return "merged"


def apply_item(item, src_base_dir, home_target, vars, vault_enabled):
    # type: (manifest.Item, str, str, Dict[str, str], bool) -> str
    src = os.path.join(src_base_dir, item.path)
    target = os.path.join(home_target, item.path)
    if item.mode == "symlink":
        return apply_symlink(src, target)
    if item.mode == "template":
        return apply_template(src, target, vars, vault_enabled)
    if item.mode == "merge":
        return apply_merge_json(src, target)
    raise ValueError("unknown mode: " + repr(item.mode))


def apply_layer(items, layer, src_base_dir, home_target, vars, vault_enabled, os_name):
    # type: (List[manifest.Item], str, str, str, Dict[str, str], bool, str) -> List[Tuple[str, str]]
    results = []  # type: List[Tuple[str, str]]
    for item in items:
        if item.layer != layer:
            continue
        if not manifest.applies_to_os(item, os_name):
            continue
        result = apply_item(item, src_base_dir, home_target, vars, vault_enabled)
        results.append((item.path, result))
    return results
