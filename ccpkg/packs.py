"""Skill & Agent Packs — best-effort CLI install (spec: 2026-06-12).

Stdlib only. Python 3.9 syntax. Never raises; returns id -> status dicts.
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List

from . import osenv


@dataclass
class Pack:
    id: str
    group: str          # "Skills" | "Agents"
    desc: str
    method: str         # "marketplace" | "npx" | "gitcopy"
    marketplace: str = ""   # e.g. "anthropics/skills"
    plugins: tuple = field(default_factory=tuple)   # plugin ids to install after marketplace add
    npx_args: tuple = field(default_factory=tuple)  # args passed after "npx"
    setup_note: str = ""    # printed after a successful install
    git_repo: str = ""      # https URL for gitcopy
    default: bool = False


PACKS = [
    Pack(
        id="anthropic-skills",
        group="Skills",
        desc="Anthropic official agent skills: document-skills and example-skills",
        method="marketplace",
        marketplace="anthropics/skills",
        plugins=("document-skills@anthropic-agent-skills",
                 "example-skills@anthropic-agent-skills"),
    ),
    Pack(
        id="mattpocock-skills",
        group="Skills",
        desc="Matt Pocock's TypeScript/tooling skills via npx",
        method="npx",
        npx_args=("-y", "skills@latest", "add", "mattpocock/skills"),
        setup_note="/setup-matt-pocock-skills",
    ),
    Pack(
        id="composio-skills",
        group="Skills",
        desc="ComposioHQ awesome-claude-skills (~864 skills) — LARGE, default off",
        method="gitcopy",
        git_repo="https://github.com/ComposioHQ/awesome-claude-skills",
    ),
    Pack(
        id="wshobson-agents",
        group="Agents",
        desc="wshobson/agents marketplace (192 agents / 84 plugins) — register only",
        method="marketplace",
        marketplace="wshobson/agents",
        plugins=(),
    ),
    Pack(
        id="voltagent-subagents",
        group="Agents",
        desc="VoltAgent awesome-claude-code-subagents marketplace (154+) — register only",
        method="marketplace",
        marketplace="VoltAgent/awesome-claude-code-subagents",
        plugins=(),
    ),
    Pack(
        id="awesome-cc-toolkit",
        group="Agents",
        desc="rohitg00 awesome-claude-code-toolkit marketplace (135 agents/35 skills/42 cmds) — register",
        method="marketplace",
        marketplace="rohitg00/awesome-claude-code-toolkit",
        plugins=(),
    ),
]


def _cache_dir_for(pack_id):
    # type: (str) -> str
    return os.path.join(os.path.expanduser("~/.cache/ccpkg/packs"), pack_id)


def _sanitize_name(name):
    # type: (str) -> str
    """Lowercase, replace non-alphanumeric/hyphen chars with hyphens."""
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")


def _unique_name(base, existing):
    # type: (str, set) -> str
    """Return base if not in existing; else base-2, base-3, … ."""
    if base not in existing:
        return base
    i = 2
    while True:
        candidate = "%s-%d" % (base, i)
        if candidate not in existing:
            return candidate
        i += 1


def _gitcopy_pack(pack, run, have, home):
    # type: (Pack, object, object, str) -> str
    """Clone/pull the pack repo and copy each SKILL.md parent dir into home/skills/."""
    if not have("git"):
        return "skipped"
    cache = _cache_dir_for(pack.id)
    git_dir = os.path.join(cache, ".git")
    try:
        if os.path.isdir(git_dir):
            run(["git", "-C", cache, "pull", "--ff-only"])
        else:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            run(["git", "clone", "--depth", "1", pack.git_repo, cache])
    except Exception:
        return "failed"

    skills_home = os.path.join(home, "skills")
    try:
        os.makedirs(skills_home, exist_ok=True)
    except Exception:
        return "failed"

    existing_names = {
        d for d in os.listdir(skills_home)
        if os.path.isdir(os.path.join(skills_home, d))
    }  # type: set

    copied = 0
    for dirpath, _dirnames, filenames in os.walk(cache):
        if "SKILL.md" in filenames:
            skill_name = _sanitize_name(os.path.basename(dirpath))
            dest_name = _unique_name(skill_name, existing_names)
            dest = os.path.join(skills_home, dest_name)
            try:
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.copytree(dirpath, dest)
                existing_names.add(dest_name)
                copied += 1
            except Exception:
                pass  # best-effort: skip individual copy failures

    return "installed"


def cli_install(run=subprocess.run, have=osenv.have, home=None, only=None):
    # type: (...) -> Dict[str, str]
    """Best-effort install of PACKS. Returns id -> status mapping.

    Statuses: "installed" | "skipped" | "failed" | "partial".
    `only` is an optional set of pack ids to restrict installation.
    `home` is the ~/.claude target; defaults to os.path.expanduser("~/.claude").
    Never raises."""
    if home is None:
        home = os.path.expanduser("~/.claude")

    targets = [p for p in PACKS if only is None or p.id in only]
    result = {}  # type: Dict[str, str]

    for pack in targets:
        try:
            status = _install_one(pack, run, have, home)
        except Exception:
            status = "failed"
        result[pack.id] = status

    return result


def _install_one(pack, run, have, home):
    # type: (Pack, object, object, str) -> str
    """Install a single pack; returns a status string. May raise on unexpected
    errors — the caller in cli_install catches and maps to "failed"."""
    if pack.method == "marketplace":
        return _marketplace_pack(pack, run, have)
    if pack.method == "npx":
        return _npx_pack(pack, run, have)
    if pack.method == "gitcopy":
        return _gitcopy_pack(pack, run, have, home)
    return "failed"


def _marketplace_pack(pack, run, have):
    # type: (Pack, object, object) -> str
    if not have("claude"):
        return "skipped"

    # Add the marketplace — required even when no plugins to install.
    marketplace_ok = True
    try:
        run(["claude", "plugin", "marketplace", "add", pack.marketplace])
    except Exception:
        marketplace_ok = False

    # Agent-only packs: empty plugins list means registering the marketplace is all.
    if not pack.plugins:
        return "installed" if marketplace_ok else "failed"

    # Cannot proceed to plugin installs if marketplace add failed.
    if not marketplace_ok:
        return "failed"

    installed = 0
    failed = 0
    for plugin in pack.plugins:
        try:
            run(["claude", "plugin", "install", plugin])
            installed += 1
        except Exception:
            failed += 1

    if failed == 0:
        return "installed"
    if installed == 0:
        return "failed"
    return "partial"


def _npx_pack(pack, run, have):
    # type: (Pack, object, object) -> str
    if not have("npx"):
        return "skipped"
    try:
        run(["npx"] + list(pack.npx_args))
        return "installed"
    except Exception:
        return "failed"


def setup_notes(statuses):
    # type: (Dict[str, str]) -> List[str]
    """Return one setup note per installed pack that declares a setup_note."""
    by_id = {p.id: p for p in PACKS}
    notes = []  # type: List[str]
    for pack_id, status in statuses.items():
        if status == "installed":
            pack = by_id.get(pack_id)
            if pack and pack.setup_note:
                notes.append(pack.setup_note)
    return notes
