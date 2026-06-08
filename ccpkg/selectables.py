"""Declarative non-file installables (plugins + mailbox) for the install wizard.

Stdlib only, Python 3.9. These carry the same presentation shape as manifest
Items (group/desc/default) plus an `id` and a `kind` so the installer knows how
to act on a selected entry.
"""
from dataclasses import dataclass


@dataclass
class Selectable:
    id: str
    kind: str          # "plugin" | "mailbox"
    group: str
    desc: str
    default: bool = True


SELECTABLES = [
    Selectable(id="superpowers", kind="plugin", group="Plugins",
               desc="skill bundle: brainstorming, TDD, systematic debugging, plan writing", default=True),
    Selectable(id="frontend-design", kind="plugin", group="Plugins",
               desc="generates distinctive, non-generic production-grade frontend UIs", default=True),
    Selectable(id="understand-anything", kind="plugin", group="Plugins",
               desc="build interactive codebase knowledge graphs & guided tours", default=True),
    Selectable(id="mailbox", kind="mailbox", group="Coordination",
               desc="cross-session file-claim coordinator so parallel agents don't clobber edits", default=True),
]
