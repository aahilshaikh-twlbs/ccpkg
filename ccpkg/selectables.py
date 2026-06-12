"""Declarative non-file installables (plugins + mboard + packs) for the install wizard.

Stdlib only, Python 3.9. These carry the same presentation shape as manifest
Items (group/desc/default) plus an `id` and a `kind` so the installer knows how
to act on a selected entry.
"""
from dataclasses import dataclass


@dataclass
class Selectable:
    id: str
    kind: str          # "plugin" | "mboard" | "pack"
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
    Selectable(id="mboard", kind="mboard", group="Coordination",
               desc="cross-session file-claim coordinator so parallel agents don't clobber edits", default=True),
    # Skill packs (opt-in, default=False keeps the shareable base lean)
    Selectable(id="anthropic-skills", kind="pack", group="Skills",
               desc="Anthropic official agent skills: document-skills and example-skills", default=False),
    Selectable(id="mattpocock-skills", kind="pack", group="Skills",
               desc="Matt Pocock's TypeScript/tooling skills via npx", default=False),
    Selectable(id="composio-skills", kind="pack", group="Skills",
               desc="ComposioHQ awesome-claude-skills (~864 skills) — LARGE, default off", default=False),
    # Agent packs (opt-in, default=False)
    Selectable(id="wshobson-agents", kind="pack", group="Agents",
               desc="wshobson/agents marketplace (192 agents / 84 plugins) — register only", default=False),
    Selectable(id="voltagent-subagents", kind="pack", group="Agents",
               desc="VoltAgent awesome-claude-code-subagents marketplace (154+) — register only", default=False),
    Selectable(id="awesome-cc-toolkit", kind="pack", group="Agents",
               desc="rohitg00 awesome-claude-code-toolkit marketplace (135 agents/35 skills/42 cmds)", default=False),
]
