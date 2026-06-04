"""JSON deep-merge for settings files (Contract §7). Stdlib only, Python 3.9."""

import json
from typing import Any


def _copy_value(value):
    # type: (Any) -> Any
    # Deep copy of a JSON-ish value so the returned structure shares no
    # mutable references with either input. (json only yields dict/list/scalars.)
    if isinstance(value, dict):
        return {k: _copy_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy_value(v) for v in value]
    return value


def deep_merge(into, src):
    # type: (dict, dict) -> dict
    """Recursively merge ``src`` onto ``into`` and return a NEW dict.

    - dict values are merged key-by-key (recursive);
    - on any scalar/list conflict ``src`` wins;
    - lists are REPLACED by ``src`` (never concatenated);
    - neither ``into`` nor ``src`` is mutated; the result shares no
      mutable references with either input.
    """
    result = {k: _copy_value(v) for k, v in into.items()}
    for key, src_value in src.items():
        into_value = result.get(key)
        if isinstance(into_value, dict) and isinstance(src_value, dict):
            result[key] = deep_merge(into_value, src_value)
        else:
            result[key] = _copy_value(src_value)
    return result


def merge_settings_file(live_path, base_obj):
    # type: (str, dict) -> dict
    """Load the live settings JSON and merge base-managed keys on top.

    Loads ``live_path`` as JSON; on a missing file or any malformed/decode
    error the live side is treated as ``{}``. Returns
    ``deep_merge(live, base_obj)`` so ``base_obj`` (the ``src``) wins on
    conflicts (base-managed keys are authoritative) while live-only keys
    are preserved.
    """
    try:
        with open(live_path, "r") as fh:
            live = json.load(fh)
    except (OSError, ValueError):
        live = {}
    if not isinstance(live, dict):
        live = {}
    return deep_merge(live, base_obj)
