"""Capture live files back into the repo layer working trees (Contract section 13).

classify() maps a relative path to its manifest layer (or None for unknown).
push() reverse-templatizes machine values to ${VAR}, steers unknown files toward
"overlay" when scan_text_purity trips, blocks anything carrying a secret, and
writes into home/.claude (base) or OVERLAY_DIR (overlay). No git commit. stdlib
only, Python 3.9.
"""
import os
from typing import Dict, List, Optional

from . import config
from . import localenv
from . import manifest
from . import scan
from . import template


def classify(path_rel, items):
    # type: (str, List[manifest.Item]) -> Optional[str]
    """Return the layer of the manifest item matching path_rel, else None."""
    for item in items:
        if item.path == path_rel:
            return item.layer
    return None


def _read(path):
    # type: (str) -> Optional[str]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (IOError, OSError):
        return None


def _layer_dest_root(layer, root, env):
    # type: (str, str, Dict[str, str]) -> Optional[str]
    """Working-tree root for a layer: base => home/.claude, overlay => OVERLAY_DIR."""
    if layer == "base":
        return config.home_claude_src(root)
    if layer == "overlay":
        overlay_dir = env.get("OVERLAY_DIR", "")
        if overlay_dir:
            return overlay_dir
        return None
    return None


def push(root, home_target, env, paths,
         confirm=lambda p: "base", os_name="darwin"):
    # type: (str, str, Dict[str, str], List[str], object, str) -> Dict[str, object]
    """Capture changed live files into the right layer working tree (no commit)."""
    written = []   # type: List[str]
    skipped = []   # type: List[str]
    blocked = []   # type: List[str]

    items = manifest.parse(config.manifest_path(root))
    vars = localenv.template_vars(env)
    terms = scan.load_purity_terms(root)

    for path_rel in paths:
        live_path = os.path.join(home_target, path_rel)
        live_text = _read(live_path)
        if live_text is None:
            skipped.append(path_rel)
            continue

        # Reverse-templatize machine values back to ${VAR} for repo storage.
        captured = template.reverse_substitute(live_text, vars)

        # Decide the layer: manifest classification, else purity-steered suggestion.
        layer = classify(path_rel, items)
        if layer is None:
            purity = scan.scan_text_purity(captured, terms, path_rel)
            suggestion = "overlay" if purity else "base"
            layer = confirm(suggestion)
        else:
            layer = confirm(layer)

        dest_root = _layer_dest_root(layer, root, env)
        if dest_root is None:
            skipped.append(path_rel)
            continue

        # Compare against the repo's current content; skip if no effective change.
        dest_path = os.path.join(dest_root, path_rel)
        repo_text = _read(dest_path)
        if repo_text is not None and repo_text == captured:
            skipped.append(path_rel)
            continue

        # Secrets MUST be clean; otherwise refuse to write and record as blocked.
        secret_findings = scan.scan_text_secrets(captured, path_rel)
        if not scan.is_clean(secret_findings):
            blocked.append(path_rel)
            continue

        parent = os.path.dirname(dest_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as fh:
            fh.write(captured)
        written.append(path_rel)

    return {"written": written, "skipped": skipped, "blocked": blocked}
