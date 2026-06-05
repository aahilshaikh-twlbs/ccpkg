import json

import pytest

from ccpkg import manifest


def _write_manifest(tmp_path, obj):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(obj))
    return str(p)


def test_parse_valid_returns_items(tmp_path):
    path = _write_manifest(
        tmp_path,
        {
            "items": [
                {
                    "path": "settings.json",
                    "mode": "merge",
                    "os": "any",
                    "layer": "base",
                },
                {
                    "path": "statusline.sh",
                    "mode": "symlink",
                    "os": "darwin",
                    "layer": "base",
                },
                {
                    "path": "settings.local.json.tmpl",
                    "mode": "template",
                    "os": "linux",
                    "layer": "overlay",
                },
            ]
        },
    )

    items = manifest.parse(path)

    assert len(items) == 3
    assert all(isinstance(i, manifest.Item) for i in items)
    assert items[0].path == "settings.json"
    assert items[0].mode == "merge"
    assert items[0].os == "any"
    assert items[0].layer == "base"
    assert items[1].mode == "symlink"
    assert items[1].os == "darwin"
    assert items[2].mode == "template"
    assert items[2].layer == "overlay"


def test_parse_applies_default_os_and_layer(tmp_path):
    path = _write_manifest(
        tmp_path,
        {"items": [{"path": "skills/shannon", "mode": "symlink"}]},
    )

    items = manifest.parse(path)

    assert len(items) == 1
    assert items[0].path == "skills/shannon"
    assert items[0].mode == "symlink"
    assert items[0].os == "any"
    assert items[0].layer == "base"


def test_parse_bad_mode_raises_value_error(tmp_path):
    path = _write_manifest(
        tmp_path,
        {"items": [{"path": "settings.json", "mode": "copy"}]},
    )

    with pytest.raises(ValueError):
        manifest.parse(path)


def test_parse_bad_os_raises_value_error(tmp_path):
    path = _write_manifest(
        tmp_path,
        {"items": [{"path": "a", "mode": "symlink", "os": "windows"}]},
    )

    with pytest.raises(ValueError):
        manifest.parse(path)


def test_parse_bad_layer_raises_value_error(tmp_path):
    path = _write_manifest(
        tmp_path,
        {"items": [{"path": "a", "mode": "symlink", "layer": "extra"}]},
    )

    with pytest.raises(ValueError):
        manifest.parse(path)


def test_parse_missing_path_raises_value_error(tmp_path):
    path = _write_manifest(
        tmp_path,
        {"items": [{"mode": "symlink"}]},
    )

    with pytest.raises(ValueError):
        manifest.parse(path)


def test_applies_to_os_any_matches_everything():
    item = manifest.Item(path="a", mode="symlink", os="any", layer="base")
    assert manifest.applies_to_os(item, "darwin") is True
    assert manifest.applies_to_os(item, "linux") is True


def test_applies_to_os_specific_filters():
    darwin_item = manifest.Item(path="a", mode="symlink", os="darwin", layer="base")
    assert manifest.applies_to_os(darwin_item, "darwin") is True
    assert manifest.applies_to_os(darwin_item, "linux") is False


def test_parse_reads_presentation_metadata(tmp_path):
    path = _write_manifest(
        tmp_path,
        {"items": [
            {"path": "skills/shannon", "mode": "symlink", "group": "Skills",
             "desc": "autonomous pentester", "default": True, "required": False},
        ]},
    )
    items = manifest.parse(path)
    assert items[0].group == "Skills"
    assert items[0].desc == "autonomous pentester"
    assert items[0].default is True
    assert items[0].required is False


def test_parse_presentation_metadata_defaults(tmp_path):
    # An entry with no presentation fields parses with safe defaults (backward compat).
    path = _write_manifest(
        tmp_path,
        {"items": [{"path": "settings.json", "mode": "merge"}]},
    )
    item = manifest.parse(path)[0]
    assert item.group == "Core"
    assert item.desc == ""
    assert item.default is True
    assert item.required is False


def test_repo_manifest_items_are_grouped():
    # The real shipped manifest annotates every base item with a non-empty group.
    from ccpkg import config
    items = manifest.parse(config.manifest_path(config.repo_root()))
    groups = {i.group for i in items}
    assert "Core" in groups
    assert "Commands" in groups
    assert "Skills" in groups
    # every item has a human description
    assert all(i.desc for i in items)
