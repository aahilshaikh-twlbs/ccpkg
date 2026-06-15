"""Starter templates (Contract: §4 adoption features).

A template is a curated, committed `ccpkg.share.json` shipped in-repo under
`templates/<name>/`. `ccpkg apply <name>` resolves a known template name to its
shipped share dict and reuses the shared-setup adopt path (share.resolve_selection
-> profile -> install). So a template is just a first-party, vetted "shared setup".

Stdlib only, Python 3.9.
"""

import os
from typing import List, Optional

from . import config
from . import share


def templates_dir(root=None):
    # type: (Optional[str]) -> str
    root = root or config.repo_root()
    return os.path.join(root, "templates")


def list_templates(root=None):
    # type: (Optional[str]) -> List[str]
    """Sorted names of shipped templates (dirs under templates/ that contain a
    ccpkg.share.json). Returns [] if the templates dir is absent."""
    base = templates_dir(root)
    if not os.path.isdir(base):
        return []
    names = []
    for name in os.listdir(base):
        share_file = os.path.join(base, name, share.SHARE_FILENAME)
        if os.path.isfile(share_file):
            names.append(name)
    return sorted(names)


def template_path(name, root=None):
    # type: (str, Optional[str]) -> str
    return os.path.join(templates_dir(root), name, share.SHARE_FILENAME)


def resolve_template(name, root=None):
    # type: (str, Optional[str]) -> Optional[dict]
    """Parsed share dict for a known template name, or None if `name` is not a
    shipped template (so `apply` dispatch falls through to url/path). Raises
    ValueError only if a shipped template file is itself malformed."""
    if name not in list_templates(root):
        return None
    return share._read_share(template_path(name, root))
