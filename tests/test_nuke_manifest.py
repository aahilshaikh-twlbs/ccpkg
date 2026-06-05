import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _items():
    return json.loads((ROOT / "manifest.json").read_text())["items"]


def test_nuke_command_and_hook_are_declared():
    paths = {i["path"]: i for i in _items()}
    for p in ("commands/nuke.md", "hooks/nuke.py"):
        assert p in paths, f"{p} missing from manifest"
        item = paths[p]
        assert item["mode"] == "symlink"
        assert item["os"] == "any"
        assert item["layer"] == "base"


def test_declared_nuke_files_exist_on_disk():
    for p in ("commands/nuke.md", "hooks/nuke.py"):
        assert (ROOT / "home" / ".claude" / p).is_file(), f"{p} not on disk"
