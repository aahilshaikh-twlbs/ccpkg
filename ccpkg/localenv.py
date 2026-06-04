"""Per-machine variable resolution (Contract §3).

Stdlib only; Python 3.9 syntax (typing.Dict, no match / no X | Y).
No shell execution and no command substitution: values are parsed and expanded
purely as text against os.environ plus a caller-supplied env mapping.
"""

import os
import re
from typing import Dict

DEFAULTS = {
    "CODE_ROOT": "$HOME/Documents/Code",
    "VAULT_ROOT": "",
    "AWS_PROFILE": "",
    "OVERLAY_REPO": "",
    "OVERLAY_DIR": "",
}

# $VAR or ${VAR}. A bare '$' or '$(' (command substitution) does not match,
# so it is left verbatim — there is no shell evaluation.
_VAR_RE = re.compile(r"\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)")


def _strip_quotes(value):
    # type: (str) -> str
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_env_text(text):
    # type: (str) -> Dict[str, str]
    """Parse KEY=VALUE lines. Ignore blanks/#comments, strip quotes. No shell exec."""
    out = {}  # type: Dict[str, str]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        out[key] = _strip_quotes(value.strip())
    return out


def expand(value, env):
    # type: (str, Dict[str, str]) -> str
    """Expand $VAR / ${VAR} (incl. $HOME) from env overlaid on os.environ.

    Only variable references are expanded. Unknown variables are left as-is.
    No command substitution is performed.
    """
    lookup = dict(os.environ)
    lookup.update(env)

    def _repl(match):
        # type: (re.Match) -> str
        name = match.group("braced") or match.group("bare")
        if name in lookup:
            return lookup[name]
        return match.group(0)

    return _VAR_RE.sub(_repl, value)


def load(path):
    # type: (str) -> Dict[str, str]
    """DEFAULTS overlaid with the parsed file (if it exists); every value expanded.

    Missing file -> expanded DEFAULTS. Returns a new merged dict.
    """
    merged = dict(DEFAULTS)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            merged.update(parse_env_text(fh.read()))
    result = {}  # type: Dict[str, str]
    for key, value in merged.items():
        result[key] = expand(value, result)
    return result


def template_vars(env):
    # type: (Dict[str, str]) -> Dict[str, str]
    """The dict used for ${VAR} substitution: HOME plus CODE_ROOT/VAULT_ROOT/AWS_PROFILE."""
    return {
        "HOME": os.path.expanduser("~"),
        "CODE_ROOT": env.get("CODE_ROOT", ""),
        "VAULT_ROOT": env.get("VAULT_ROOT", ""),
        "AWS_PROFILE": env.get("AWS_PROFILE", ""),
    }
