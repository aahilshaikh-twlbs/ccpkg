"""Template substitution and optional vault-block handling (Contract section 6).

Pure functions, stdlib only. Used by apply.py (render templates on install/pull)
and push.py (reverse_substitute machine values back to ${VAR}).
"""
import re
from typing import Dict

VAULT_BEGIN = "# ccpkg:vault:start"   # line markers (also work as <!-- ccpkg:vault:start -->)
VAULT_END = "# ccpkg:vault:end"

# matches ${NAME} where NAME is an identifier-ish token.
_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# A marker line is any line whose stripped form, after removing optional HTML
# comment wrappers, equals the vault begin/end marker text.
_HTML_OPEN = "<!--"
_HTML_CLOSE = "-->"

# the only vars reverse_substitute will turn back into ${VAR} (never HOME).
_REVERSIBLE_VARS = ("CODE_ROOT", "VAULT_ROOT", "AWS_PROFILE")


def substitute(text, vars):
    # type: (str, Dict[str, str]) -> str
    """Replace ${VAR} with vars[VAR]; leave unknown ${VAR} untouched."""
    def _repl(match):
        name = match.group(1)
        if name in vars:
            return vars[name]
        return match.group(0)
    return _VAR_RE.sub(_repl, text)


def _marker_kind(line):
    # type: (str) -> str
    """Return "start", "end", or "" for a (possibly HTML/# wrapped) marker line."""
    stripped = line.strip()
    if stripped.startswith(_HTML_OPEN) and stripped.endswith(_HTML_CLOSE):
        stripped = stripped[len(_HTML_OPEN):-len(_HTML_CLOSE)].strip()
    # the marker constants already carry a leading "# "; normalize the candidate
    # to compare both the "# ccpkg:vault:start" and "ccpkg:vault:start" forms.
    begin_bare = VAULT_BEGIN[len("# "):] if VAULT_BEGIN.startswith("# ") else VAULT_BEGIN
    end_bare = VAULT_END[len("# "):] if VAULT_END.startswith("# ") else VAULT_END
    if stripped == VAULT_BEGIN or stripped == begin_bare:
        return "start"
    if stripped == VAULT_END or stripped == end_bare:
        return "end"
    return ""


def strip_optional_blocks(text, enabled):
    # type: (str, bool) -> str
    """Handle vault begin/end marker blocks.

    enabled=False: drop everything from a start marker through its end marker
                   (inclusive). enabled=True: drop only the marker lines, keep
                   the content. Tolerant of HTML-comment / # comment wrappers
                   and surrounding whitespace on the marker lines.
    """
    out_lines = []
    in_block = False
    # splitlines(keepends=True) preserves the original newline of each line so
    # we reproduce the input's line endings exactly.
    for line in text.splitlines(keepends=True):
        kind = _marker_kind(line)
        if kind == "start":
            in_block = True
            # marker line itself is always removed (both modes).
            continue
        if kind == "end":
            in_block = False
            continue
        if in_block and not enabled:
            # inside a disabled block: drop content.
            continue
        out_lines.append(line)
    return "".join(out_lines)


def render(text, vars, vault_enabled):
    # type: (str, Dict[str, str], bool) -> str
    """substitute then strip optional blocks (Contract section 6)."""
    return strip_optional_blocks(substitute(text, vars), vault_enabled)


def reverse_substitute(text, vars):
    # type: (str, Dict[str, str]) -> str
    """Replace machine VALUES with ${VAR} for push.

    Only CODE_ROOT / VAULT_ROOT / AWS_PROFILE are reversed (never HOME, to avoid
    ambiguity). Empty values are skipped. Longest values are replaced first so a
    value that is a prefix of another is not partially consumed.
    """
    # collect (value, name) pairs for non-empty reversible vars, longest first.
    pairs = []
    for name in _REVERSIBLE_VARS:
        value = vars.get(name, "")
        if value:
            pairs.append((value, name))
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    for value, name in pairs:
        text = text.replace(value, "${" + name + "}")
    return text
