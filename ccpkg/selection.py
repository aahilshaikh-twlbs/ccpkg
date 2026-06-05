"""Compose stages from manifest items + selectables, and resolve the selected
set via the precedence ladder. Stdlib only, Python 3.9.

ID convention: a manifest item's id is its `path`; a selectable's id is its `id`.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from . import manifest as manifest_mod
from . import selectables as selectables_mod

# Stage display order. A group not listed here sorts last, alphabetically.
STAGE_ORDER = ["Core", "Commands", "Skills", "Plugins", "Coordination", "Overlay"]


@dataclass
class Entry:
    id: str
    desc: str
    default: bool
    kind: str          # "file" | "plugin" | "mailbox"


@dataclass
class Stage:
    name: str
    entries: List[Entry] = field(default_factory=list)


def _order_key(group):
    # type: (str) -> tuple
    if group in STAGE_ORDER:
        return (0, STAGE_ORDER.index(group), "")
    return (1, 0, group)


def build_stages(items, sels, overlay_present):
    # type: (List, List, bool) -> List[Stage]
    """Group manifest items + selectables into ordered stages. Overlay-layer
    items are included only when overlay_present is True. Empty stages dropped."""
    buckets = {}  # type: Dict[str, List[Entry]]
    for it in items:
        if it.layer == "overlay" and not overlay_present:
            continue
        buckets.setdefault(it.group, []).append(
            Entry(id=it.path, desc=it.desc, default=it.default, kind="file"))
    for s in sels:
        buckets.setdefault(s.group, []).append(
            Entry(id=s.id, desc=s.desc, default=s.default, kind=s.kind))

    stages = []
    for group in sorted(buckets, key=_order_key):
        entries = buckets[group]
        if entries:
            stages.append(Stage(name=group, entries=entries))
    return stages


def default_ids(items, sels, overlay_present):
    # type: (List, List, bool) -> Set[str]
    out = set()  # type: Set[str]
    for stage in build_stages(items, sels, overlay_present):
        for e in stage.entries:
            if e.default:
                out.add(e.id)
    return out


def resolve_selection(items, sels, overlay_present, profile_obj, is_tty,
                      reconfigure, run_wizard):
    # type: (List, List, bool, object, bool, bool, Optional[Callable]) -> Set[str]
    """Precedence ladder -> the set of selected ids.

    --reconfigure : run wizard (pre-ticked from profile.selected if any, else defaults)
    profile present: use profile.selected verbatim
    is_tty         : run wizard (pre-ticked from defaults)
    else           : default:true entries
    """
    defaults = default_ids(items, sels, overlay_present)
    stages = build_stages(items, sels, overlay_present)

    if reconfigure and run_wizard is not None:
        if profile_obj is not None:
            preselected = set(profile_obj.selected)
        else:
            preselected = set(defaults)
        return set(run_wizard(stages, preselected))

    if profile_obj is not None:
        return set(profile_obj.selected)

    if is_tty and run_wizard is not None:
        return set(run_wizard(stages, set(defaults)))

    return set(defaults)
