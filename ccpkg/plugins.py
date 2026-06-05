"""Plugin + marketplace settings and best-effort CLI install (contract section 10).

Stdlib only. Python 3.9 syntax.
"""

import copy
import subprocess
from typing import Dict

from . import osenv

PLUGINS = [
    "superpowers@claude-plugins-official",
    "frontend-design@claude-plugins-official",
    "understand-anything@understand-anything",
]

MARKETPLACES = {
    "understand-anything": {
        "source": {"source": "github", "repo": "Lum1104/Understand-Anything"}
    }
}

# github "owner/repo" used for `claude plugin marketplace add`
_MARKETPLACE_ADD_ARG = "Lum1104/Understand-Anything"


def ensure_plugin_settings(settings):
    # type: (dict) -> dict
    """Return a NEW settings dict with every PLUGINS entry enabled (True) and
    every MARKETPLACES entry present under extraKnownMarketplaces. Existing
    unrelated entries are preserved; the input is never mutated. Idempotent."""
    out = copy.deepcopy(settings) if settings else {}

    enabled = out.get("enabledPlugins")
    if not isinstance(enabled, dict):
        enabled = {}
    for plugin in PLUGINS:
        enabled[plugin] = True
    out["enabledPlugins"] = enabled

    markets = out.get("extraKnownMarketplaces")
    if not isinstance(markets, dict):
        markets = {}
    for name, spec in MARKETPLACES.items():
        markets[name] = copy.deepcopy(spec)
    out["extraKnownMarketplaces"] = markets

    return out


def cli_install(run=subprocess.run, have=osenv.have, only=None):
    # type: (..., object) -> Dict[str, str]
    """Best-effort install of PLUGINS via the `claude` CLI. If `claude` is not
    present, every plugin is "skipped" and nothing is executed. Otherwise add
    the marketplace then install each plugin; a plugin maps to "installed" on
    success or "failed" if its install command errors. Never raises.

    When `only` is a set of plugin ids, restrict the targets to that subset."""
    targets = list(PLUGINS) if only is None else [p for p in PLUGINS if p in only]
    if not have("claude"):
        return {plugin: "skipped" for plugin in targets}

    # marketplace add is best-effort; failure here does not abort installs.
    try:
        run(["claude", "plugin", "marketplace", "add", _MARKETPLACE_ADD_ARG])
    except Exception:
        pass

    status = {}  # type: Dict[str, str]
    for plugin in targets:
        try:
            run(["claude", "plugin", "install", plugin])
            status[plugin] = "installed"
        except Exception:
            status[plugin] = "failed"
    return status
