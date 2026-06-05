"""Persisted install selection: ~/.claude/.ccpkg-profile.json (contract addendum).

Stdlib only, Python 3.9. `selected` and `deselected` are both explicit so a
newly-added feature can default-on without being silently suppressed by an
older profile.
"""
import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

PROFILE_NAME = ".ccpkg-profile.json"


@dataclass
class Profile:
    selected: List[str] = field(default_factory=list)
    deselected: List[str] = field(default_factory=list)


def _path(home):
    # type: (str) -> str
    return os.path.join(home, PROFILE_NAME)


def load(home):
    # type: (str) -> Optional[Profile]
    """Return the saved Profile, or None if missing/unreadable/corrupt."""
    try:
        with open(_path(home), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        sel = data.get("selected", [])
        des = data.get("deselected", [])
        if not isinstance(sel, list) or not isinstance(des, list):
            return None
        return Profile(selected=[str(x) for x in sel],
                       deselected=[str(x) for x in des])
    except (OSError, ValueError):
        return None


def save(home, prof):
    # type: (str, Profile) -> None
    """Write the profile atomically-ish (write then replace). Never raises on
    a missing home dir it can create."""
    os.makedirs(home, exist_ok=True)
    tmp = _path(home) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"selected": prof.selected, "deselected": prof.deselected},
                  fh, indent=2)
        fh.write("\n")
    os.replace(tmp, _path(home))
