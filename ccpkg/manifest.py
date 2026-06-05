import json
from dataclasses import dataclass
from typing import List

VALID_MODES = ("symlink", "template", "merge")
VALID_OS = ("any", "darwin", "linux")
VALID_LAYERS = ("base", "overlay")


@dataclass
class Item:
    path: str
    mode: str
    os: str = "any"
    layer: str = "base"
    group: str = "Core"
    desc: str = ""
    default: bool = True
    required: bool = False


def _build_item(entry, index):
    if not isinstance(entry, dict):
        raise ValueError("manifest item %d is not an object" % index)

    path = entry.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("manifest item %d missing 'path'" % index)

    mode = entry.get("mode")
    if mode not in VALID_MODES:
        raise ValueError(
            "manifest item %d ('%s') has invalid mode %r; expected one of %s"
            % (index, path, mode, VALID_MODES)
        )

    os_name = entry.get("os", "any")
    if os_name not in VALID_OS:
        raise ValueError(
            "manifest item %d ('%s') has invalid os %r; expected one of %s"
            % (index, path, os_name, VALID_OS)
        )

    layer = entry.get("layer", "base")
    if layer not in VALID_LAYERS:
        raise ValueError(
            "manifest item %d ('%s') has invalid layer %r; expected one of %s"
            % (index, path, layer, VALID_LAYERS)
        )

    group = entry.get("group", "Core")
    if not isinstance(group, str) or not group:
        group = "Core"
    desc = entry.get("desc", "")
    if not isinstance(desc, str):
        desc = ""
    default = entry.get("default", True)
    if not isinstance(default, bool):
        default = True
    required = entry.get("required", False)
    if not isinstance(required, bool):
        required = False

    return Item(path=path, mode=mode, os=os_name, layer=layer,
                group=group, desc=desc, default=default, required=required)


def parse(path: str) -> List[Item]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, dict):
        raise ValueError("manifest root must be an object with 'items'")

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("manifest 'items' must be a list")

    return [_build_item(entry, index) for index, entry in enumerate(raw_items)]


def applies_to_os(item: Item, os_name: str) -> bool:
    return item.os == "any" or item.os == os_name
