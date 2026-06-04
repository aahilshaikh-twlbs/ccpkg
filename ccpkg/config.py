"""ccpkg.config — repo/home path resolution (Contract §2). Stdlib-only."""

import os


def repo_root():
    # type: () -> str
    """The repo dir: realpath(this file) -> up two (ccpkg/config.py -> ccpkg -> repo)."""
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def home_target():
    # type: () -> str
    """CLAUDE_CONFIG_DIR if set, else ~/.claude. Tests inject CLAUDE_CONFIG_DIR."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def home_claude_src(root):
    # type: (str) -> str
    """The base source-of-truth mirror: <root>/home/.claude."""
    return os.path.join(root, "home", ".claude")


def manifest_path(root):
    # type: (str) -> str
    """The base-layer manifest: <root>/manifest.json."""
    return os.path.join(root, "manifest.json")


def localenv_path(root):
    # type: (str) -> str
    """The per-machine env file: <root>/local.env."""
    return os.path.join(root, "local.env")


def backup_suffix():
    # type: () -> str
    """Suffix appended when backing up an existing live file before overwrite."""
    return ".ccpkg.bak"
