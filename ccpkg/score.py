"""Setup score / audit (showcase feature): grade a Claude Code setup 0-100 and
surface strengths + concrete upgrade suggestions.

`analyze(selected, catalog)` is pure (a selected id-set + the catalog id->(group,
desc) map -> a ScoreResult), so `card` and `gallery` reuse it for any setup.
`grade_for(score)` is the shared letter-grade band.

Stdlib only, Python 3.9.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

# High-value agents whose presence anchors the "core review loop" dimension.
KEY_AGENTS = ("agents/reviewer.md", "agents/tester.md", "agents/debugger.md",
              "agents/security.md", "agents/architect.md")


@dataclass
class ScoreResult:
    score: int
    grade: str
    dimensions: List[Tuple[str, int, int]] = field(default_factory=list)  # (name, got, max)
    strengths: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)


def grade_for(score):
    # type: (int) -> str
    for cutoff, letter in ((90, "A"), (80, "B"), (70, "C"), (60, "D")):
        if score >= cutoff:
            return letter
    return "F"


def _group_of(catalog, sid):
    # type: (Dict[str, Tuple[str, str]], str) -> str
    return catalog.get(sid, ("", ""))[0]


def _by_group(catalog):
    # type: (Dict[str, Tuple[str, str]]) -> Dict[str, Set[str]]
    out = {}  # type: Dict[str, Set[str]]
    for sid, (group, _desc) in catalog.items():
        out.setdefault(group, set()).add(sid)
    return out


def _breadth_points(n_agents):
    # type: (int) -> int
    """Reward having a real spread of agents — tiered, not full-coverage, so a
    focused setup isn't punished for not installing all 40+."""
    for threshold, pts in ((12, 25), (8, 20), (4, 12), (1, 6)):
        if n_agents >= threshold:
            return pts
    return 0


def analyze(selected, catalog):
    # type: (Set[str], Dict[str, Tuple[str, str]]) -> ScoreResult
    """Score a selected id-set against the catalog. Pure + deterministic.

    Rewards a thoughtful setup (presence of the right pieces) rather than raw
    coverage, so a lean-but-sensible setup grades well and only an empty/thin
    one grades low. Dimension maxima sum to 100."""
    sel = set(selected)
    groups = _by_group(catalog)

    def _sel_in(group):
        return len(sel & groups.get(group, set()))

    n_agents = _sel_in("Agents")
    n_plugins = _sel_in("Plugins")
    n_skills = _sel_in("Skills")
    n_commands = _sel_in("Commands")
    has_mboard = "mboard" in sel
    key_present = [a for a in KEY_AGENTS if a in sel]

    plugins_skills = min(20, (10 if "superpowers" in sel else 0)
                         + (5 if n_plugins >= 2 else 0)
                         + (5 if n_skills >= 1 else 0))

    # dimensions (sum of maxima = 100)
    dims = [
        ("Core review loop", min(len(key_present) * 4, 20), 20),
        ("Agent breadth", _breadth_points(n_agents), 25),
        ("Plugins & skills", plugins_skills, 20),
        ("Coordination (mboard)", 15 if has_mboard else 0, 15),
        ("Commands", 10 if n_commands else 0, 10),
        ("Curation", 10 if len(sel) >= 5 else 0, 10),
    ]
    score = sum(got for _name, got, _max in dims)
    score = max(0, min(100, score))

    strengths = []
    if n_agents:
        strengths.append("%d agents installed" % n_agents)
    if len(key_present) == len(KEY_AGENTS):
        strengths.append("full core review loop (reviewer/tester/debugger/security/architect)")
    if has_mboard:
        strengths.append("mboard coordination enabled")
    if n_plugins:
        strengths.append("%d plugin(s) enabled" % n_plugins)

    suggestions = []
    missing_key = [a.split("/")[-1].replace(".md", "")
                   for a in KEY_AGENTS if a not in sel]
    if missing_key:
        suggestions.append("add core agents: %s" % ", ".join(missing_key))
    if not has_mboard:
        suggestions.append("enable mboard for multi-session coordination")
    if n_agents < 8:
        suggestions.append("`ccpkg apply the-works` for broader agent coverage")
    if "superpowers" not in sel:
        suggestions.append("enable the superpowers plugin")

    counts = {"agents": n_agents, "plugins": n_plugins, "skills": n_skills,
              "commands": n_commands, "mboard": int(has_mboard),
              "total_selected": len(sel)}
    return ScoreResult(score=score, grade=grade_for(score), dimensions=dims,
                       strengths=strengths, suggestions=suggestions, counts=counts)
