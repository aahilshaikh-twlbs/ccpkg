"""Setup "flex card" (showcase feature): render a shareable SVG summary of a
Claude Code setup — score, grade, and per-group counts — for a README or socials.

`build_stats` gathers the numbers (reusing score.analyze); `render_svg` turns
them into a self-contained SVG string (valid XML, no external assets, renders on
GitHub). Stdlib only, Python 3.9.
"""

from typing import Dict
from xml.sax.saxutils import escape

from . import score as score_mod
from . import share as share_mod

# grade -> accent color (GitHub-dark friendly).
_GRADE_COLOR = {"A": "#3fb950", "B": "#58a6ff", "C": "#d29922",
                "D": "#db6d28", "F": "#f85149"}

# groups shown as stat rows, in order.
_ROWS = ("Agents", "Skills", "Plugins", "Commands")


def build_stats(root, home, overlay_present=False):
    # type: (str, str, bool) -> dict
    """Gather the card's numbers from the current selection (profile or default)."""
    selected = set(share_mod.export_setup(root, home, overlay_present)["selected"])
    catalog = share_mod._catalog(root, overlay_present)
    result = score_mod.analyze(selected, catalog)
    groups = {}  # type: Dict[str, int]
    for sid in selected:
        group = catalog.get(sid, ("", ""))[0]
        groups[group] = groups.get(group, 0) + 1
    return {
        "score": result.score,
        "grade": result.grade,
        "groups": groups,
        "total": len(selected),
        "mboard": "mboard" in selected,
    }


def render_svg(stats, title="Claude Code setup"):
    # type: (dict, str) -> str
    """A self-contained SVG card. `stats` is a build_stats() dict."""
    grade = stats.get("grade", "F")
    accent = _GRADE_COLOR.get(grade, "#8b949e")
    title_esc = escape(str(title))
    groups = stats.get("groups", {})

    rows = []
    y = 132
    for name in _ROWS:
        count = int(groups.get(name, 0))
        rows.append(
            '<text x="36" y="{y}" fill="#8b949e" font-size="15">{name}</text>'
            '<text x="250" y="{y}" fill="#e6edf3" font-size="15" '
            'text-anchor="end" font-weight="600">{count}</text>'.format(
                y=y, name=escape(name), count=count))
        y += 28
    mboard = "yes" if stats.get("mboard") else "no"
    rows.append(
        '<text x="36" y="{y}" fill="#8b949e" font-size="15">Coordination</text>'
        '<text x="250" y="{y}" fill="#e6edf3" font-size="15" '
        'text-anchor="end" font-weight="600">{v}</text>'.format(y=y, v=mboard))

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="260" '
        'viewBox="0 0 480 260" role="img" aria-label="{title} card">'
        '<rect width="480" height="260" rx="14" fill="#0d1117"/>'
        '<rect x="1" y="1" width="478" height="258" rx="13" fill="none" '
        'stroke="{accent}" stroke-opacity="0.5"/>'
        '<text x="36" y="48" fill="#e6edf3" font-family="ui-sans-serif,system-ui,'
        'Segoe UI,Helvetica,Arial" font-size="22" font-weight="700">{title}</text>'
        '<text x="36" y="74" fill="#8b949e" font-family="ui-sans-serif,system-ui,'
        'Segoe UI,Helvetica,Arial" font-size="13">via ccpkg · {total} items</text>'
        '<circle cx="404" cy="64" r="42" fill="none" stroke="{accent}" '
        'stroke-width="6"/>'
        '<text x="404" y="62" fill="{accent}" text-anchor="middle" '
        'font-family="ui-sans-serif,system-ui,Segoe UI,Helvetica,Arial" '
        'font-size="30" font-weight="800">{grade}</text>'
        '<text x="404" y="84" fill="#8b949e" text-anchor="middle" '
        'font-family="ui-sans-serif,system-ui,Segoe UI,Helvetica,Arial" '
        'font-size="13">{score}/100</text>'
        '<g font-family="ui-sans-serif,system-ui,Segoe UI,Helvetica,Arial">{rows}</g>'
        '<text x="36" y="240" fill="#6e7681" font-family="ui-sans-serif,system-ui,'
        'Segoe UI,Helvetica,Arial" font-size="12">github.com · ccpkg apply</text>'
        '</svg>'
    ).format(title=title_esc, accent=accent, total=int(stats.get("total", 0)),
             grade=escape(grade), score=int(stats.get("score", 0)),
             rows="".join(rows))
