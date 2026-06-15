"""Repo-aware auto-setup (showcase feature): detect what a project IS and
recommend the Claude Code setup for working on it.

`detect(cwd)` scans a project for technology signals (bounded, shallow, never
raises). `recommend(signals, catalog)` maps signals -> catalog ids + the MCP
servers + a per-pick rationale via a declarative SIGNAL_RULES table. The CLI
applies the recommendation (selection install + ./.mcp.json) by default, or
just previews it.

Stdlib only, Python 3.9.
"""

import os
from typing import Dict, List, Set, Tuple

# --- detection ---------------------------------------------------------------

# Marker files (exact basename) -> signal.
_MARKER_FILES = {
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "Gemfile": "ruby",
    "pom.xml": "java",
    "build.gradle": "java",
    "Dockerfile": "docker",
    "docker-compose.yml": "docker",
    "docker-compose.yaml": "docker",
    "schema.prisma": "database",
    "package.json": "node",
    "go.sum": "go",
}

# File extensions -> signal (covers projects without a manifest at the root).
_EXT_SIGNALS = {
    ".rs": "rust",
    ".go": "go",
    ".py": "python",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "java",
    ".tsx": "frontend",
    ".jsx": "frontend",
    ".vue": "frontend",
    ".svelte": "frontend",
    ".sql": "database",
    ".tf": "infra",
}

# Directories that, if present, imply a signal.
_DIR_SIGNALS = {
    ".github": "ci",
    "terraform": "infra",
    "k8s": "infra",
    "kubernetes": "infra",
}

_SKIP_DIRS = frozenset([
    ".git", "node_modules", ".venv", "venv", "__pycache__", "target",
    "dist", "build", "vendor", ".next", ".cache",
])


def detect(cwd):
    # type: (str) -> Set[str]
    """Technology signals for the project rooted at `cwd`. Shallow walk
    (root + one level into immediate subdirs for extensions); never raises."""
    signals = set()  # type: Set[str]
    try:
        root_entries = os.listdir(cwd)
    except OSError:
        return signals

    for name in root_entries:
        if name in _MARKER_FILES:
            signals.add(_MARKER_FILES[name])
        full = os.path.join(cwd, name)
        if os.path.isdir(full) and name in _DIR_SIGNALS:
            signals.add(_DIR_SIGNALS[name])

    # node + react/next -> a frontend signal (read package.json best-effort)
    if "node" in signals:
        _node_frontend(cwd, signals)

    # a git remote -> github signal
    if _has_git_remote(cwd):
        signals.add("git")
        signals.add("github")

    # extension sweep: root + one level deep, capped, skipping noise dirs
    _ext_sweep(cwd, signals)
    return signals


def _node_frontend(cwd, signals):
    # type: (str, Set[str]) -> None
    try:
        with open(os.path.join(cwd, "package.json"), "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return
    lowered = text.lower()
    if any(fw in lowered for fw in ('"react"', '"next"', '"vue"', '"svelte"',
                                    '"@angular', '"vite"')):
        signals.add("frontend")
    signals.add("node")


def _has_git_remote(cwd):
    # type: (str) -> bool
    cfg = os.path.join(cwd, ".git", "config")
    try:
        with open(cfg, "r", encoding="utf-8") as fh:
            return "[remote " in fh.read()
    except OSError:
        return False


def _ext_sweep(cwd, signals):
    # type: (str, Set[str]) -> None
    seen = 0
    for base in (cwd,) + tuple(_immediate_subdirs(cwd)):
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            ext = os.path.splitext(name)[1]
            if ext in _EXT_SIGNALS:
                signals.add(_EXT_SIGNALS[ext])
            seen += 1
            if seen > 4000:   # safety cap on huge trees
                return


def _immediate_subdirs(cwd):
    # type: (str) -> List[str]
    out = []
    try:
        for name in os.listdir(cwd):
            full = os.path.join(cwd, name)
            if os.path.isdir(full) and name not in _SKIP_DIRS:
                out.append(full)
    except OSError:
        pass
    return out


# --- recommendation ----------------------------------------------------------

# Always recommended regardless of project type: the core review loop + the
# coordinator + local git access.
_BASE_IDS = ("agents/architect.md", "agents/debugger.md", "agents/reviewer.md",
             "agents/tester.md", "agents/refactor.md", "superpowers", "mboard")
_BASE_MCP = ("git",)
_BASE_WHY = "core review + coordination loop (recommended for any project)"

# signal -> (catalog ids, mcp ids, rationale).
SIGNAL_RULES = {
    "frontend": (("agents/frontend.md", "agents/a11y.md", "frontend-design"),
                 (), "frontend code detected"),
    "node":     (("agents/api-designer.md", "agents/integrator.md"),
                 (), "a Node project"),
    "rust":     (("agents/perf.md", "agents/api-designer.md"),
                 (), "a Rust project"),
    "go":       (("agents/api-designer.md", "agents/perf.md"),
                 (), "a Go project"),
    "python":   (("agents/data-engineer.md", "agents/api-designer.md"),
                 (), "a Python project"),
    "ruby":     (("agents/api-designer.md",), (), "a Ruby project"),
    "java":     (("agents/api-designer.md", "agents/architect.md"),
                 (), "a Java/Kotlin project"),
    "database": (("agents/dba.md", "agents/data-engineer.md"),
                 ("postgres", "sqlite"), "database schema/SQL detected"),
    "docker":   (("agents/containerizer.md", "agents/infra.md"),
                 (), "Docker detected"),
    "infra":    (("agents/infra.md", "agents/sre.md", "agents/ops.md"),
                 (), "infrastructure-as-code detected"),
    "ci":       (("agents/ops.md", "agents/release-manager.md"),
                 (), "CI workflows detected"),
    "github":   ((), ("github",), "a GitHub remote"),
    "git":      ((), (), "a git repo"),
}


def recommend(signals, catalog_ids):
    # type: (Set[str], Set[str]) -> Tuple[List[str], List[str], List[dict]]
    """Map signals -> (selected_ids, mcp_ids, rationale). Both id lists are
    intersected with the live catalog (unknowns dropped) and de-duped/sorted.
    `rationale` is [{"id", "why"}] for the picks the catalog actually has."""
    picks = {}   # type: Dict[str, str]   id -> why
    mcp = {}     # type: Dict[str, str]   mcp id -> why

    def _add(ids, why):
        for i in ids:
            picks.setdefault(i, why)

    def _add_mcp(ids, why):
        for i in ids:
            mcp.setdefault(i, why)

    _add(_BASE_IDS, _BASE_WHY)
    _add_mcp(_BASE_MCP, _BASE_WHY)
    for sig in signals:
        rule = SIGNAL_RULES.get(sig)
        if rule is None:
            continue
        ids, mcp_ids, why = rule
        _add(ids, why)
        _add_mcp(mcp_ids, why)

    selected = sorted(i for i in picks if i in catalog_ids)
    mcp_ids = sorted(mcp)   # mcp catalog is validated by the caller
    rationale = [{"id": i, "why": picks[i]} for i in selected]
    return selected, mcp_ids, rationale
