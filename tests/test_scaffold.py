import json
import os

import pytest

from ccpkg import manifest, scaffold


def _make_repo(tmp_path):
    """Build a minimal repo: a manifest.json with one existing item and a
    home/.claude/ dir. Returns the repo root as a str."""
    root = tmp_path
    (root / "home" / ".claude").mkdir(parents=True)
    manifest_obj = {
        "items": [
            {"path": "settings.json", "mode": "merge", "os": "any",
             "layer": "base", "group": "Core", "desc": "core", "default": True}
        ]
    }
    # Write in the compact one-object-per-line style the inserter expects.
    lines = ["{", '  "items": ['] + [
        "    " + json.dumps(it) for it in manifest_obj["items"]
    ]
    # add trailing comma logic handled by inserter; first item has none here
    text = "{\n  \"items\": [\n    " + json.dumps(manifest_obj["items"][0]) + "\n  ]\n}\n"
    (root / "manifest.json").write_text(text)
    return str(root)


def _find(items, path):
    for it in items:
        if it.path == path:
            return it
    raise AssertionError("no item with path %r" % path)


def test_create_agent(tmp_path):
    root = _make_repo(tmp_path)
    paths = scaffold.create(root, "agent", "myagent")

    file_path = os.path.join(root, "home", ".claude", "agents", "myagent.md")
    assert paths == [file_path, "manifest.json"]
    assert os.path.isfile(file_path)
    body = open(file_path, encoding="utf-8").read()
    assert "name: myagent" in body
    assert "## Method" in body

    items = manifest.parse(os.path.join(root, "manifest.json"))
    it = _find(items, "agents/myagent.md")
    assert it.mode == "symlink"
    assert it.group == "Agents"
    assert it.default is False
    assert it.layer == "base"
    assert it.os == "any"


def test_create_command(tmp_path):
    root = _make_repo(tmp_path)
    scaffold.create(root, "command", "mycmd")

    file_path = os.path.join(root, "home", ".claude", "commands", "mycmd.md")
    assert os.path.isfile(file_path)
    body = open(file_path, encoding="utf-8").read()
    assert "/mycmd" in body

    items = manifest.parse(os.path.join(root, "manifest.json"))
    it = _find(items, "commands/mycmd.md")
    assert it.mode == "symlink"
    assert it.group == "Commands"
    assert it.default is True


def test_create_hook(tmp_path):
    root = _make_repo(tmp_path)
    scaffold.create(root, "hook", "myhook")

    file_path = os.path.join(root, "home", ".claude", "hooks", "myhook.py")
    assert os.path.isfile(file_path)
    body = open(file_path, encoding="utf-8").read()
    assert body.startswith("#!/usr/bin/env python3")
    assert "json.load(sys.stdin)" in body

    items = manifest.parse(os.path.join(root, "manifest.json"))
    it = _find(items, "hooks/myhook.py")
    assert it.mode == "symlink"
    assert it.group == "Hooks"
    assert it.default is True


def test_create_skill_writes_skill_md_registers_dir(tmp_path):
    root = _make_repo(tmp_path)
    paths = scaffold.create(root, "skill", "myskill")

    file_path = os.path.join(
        root, "home", ".claude", "skills", "myskill", "SKILL.md"
    )
    assert paths[0] == file_path
    assert os.path.isfile(file_path)
    body = open(file_path, encoding="utf-8").read()
    assert "name: myskill" in body

    items = manifest.parse(os.path.join(root, "manifest.json"))
    # Registered path is the directory, not the SKILL.md file.
    it = _find(items, "skills/myskill")
    assert it.mode == "symlink"
    assert it.group == "Skills"
    assert it.default is True
    with pytest.raises(AssertionError):
        _find(items, "skills/myskill/SKILL.md")


def test_duplicate_raises(tmp_path):
    root = _make_repo(tmp_path)
    scaffold.create(root, "agent", "dupe")
    with pytest.raises(ValueError):
        scaffold.create(root, "agent", "dupe")


def test_unknown_kind_raises(tmp_path):
    root = _make_repo(tmp_path)
    with pytest.raises(ValueError):
        scaffold.create(root, "widget", "foo")


def test_invalid_name_raises(tmp_path):
    root = _make_repo(tmp_path)
    with pytest.raises(ValueError):
        scaffold.create(root, "agent", "Bad Name")
    with pytest.raises(ValueError):
        scaffold.create(root, "agent", "-leading")
    with pytest.raises(ValueError):
        scaffold.create(root, "agent", "")


def test_group_and_default_overrides(tmp_path):
    root = _make_repo(tmp_path)
    scaffold.create(root, "agent", "custom", group="Custom", default=True)

    items = manifest.parse(os.path.join(root, "manifest.json"))
    it = _find(items, "agents/custom.md")
    assert it.group == "Custom"
    assert it.default is True

    # default=False override on a normally-true kind
    scaffold.create(root, "command", "offcmd", default=False)
    items = manifest.parse(os.path.join(root, "manifest.json"))
    it = _find(items, "commands/offcmd.md")
    assert it.default is False


def test_manifest_stays_valid_json_and_preserves_existing(tmp_path):
    root = _make_repo(tmp_path)
    manifest_file = os.path.join(root, "manifest.json")

    scaffold.create(root, "agent", "one")
    scaffold.create(root, "skill", "two")
    scaffold.create(root, "hook", "three")

    # json.loads must succeed after every insertion.
    data = json.loads(open(manifest_file, encoding="utf-8").read())
    assert isinstance(data, dict)
    paths = [it["path"] for it in data["items"]]
    # original preserved
    assert "settings.json" in paths
    # new items present
    assert "agents/one.md" in paths
    assert "skills/two" in paths
    assert "hooks/three.py" in paths
    assert len(data["items"]) == 4
