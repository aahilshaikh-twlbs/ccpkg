"""ccpkg.diff — CONTENT diff between repo-managed files and the live ~/.claude.

Complements `status` / `_compute_drift` (which only report ok/drift/missing):
this module renders the actual unified diff (expected -> live) per base item.

The status semantics here MUST mirror cli._compute_drift exactly so `diff` and
`status` never disagree: same base-only + applies_to_os filtering, same
"directory source or live symlink => ok (no content compare)" rule, same
"missing target => missing", same OSError => drift fallthrough. The only
addition is computing the "expected" content (what ccpkg WOULD write) per mode
and emitting a difflib unified diff.

Stdlib only, Python 3.9 syntax (typing.Optional/List/Tuple, no match, no X | Y).
"""

import difflib
import json
import os
from typing import Dict, List, Optional, Tuple

from . import config, localenv, manifest, mergejson, template


def _vault_enabled(env):
    # type: (Dict[str, str]) -> bool
    # Mirror cli._vault_enabled: a vault is on only when VAULT_ROOT names a dir.
    vault_root = env.get("VAULT_ROOT", "")
    return bool(vault_root) and os.path.isdir(vault_root)


def _live_target(home, item):
    # type: (str, manifest.Item) -> str
    # The live path to compare against. We deliberately use the RAW item path
    # (home/<path>) with NO ".tmpl" stripping, to match cli._compute_drift's
    # `target = os.path.join(home, item.path)` EXACTLY — the contract requires
    # `diff` and `status` to never disagree, so we mirror its target resolution
    # verbatim even for template items. (apply.apply_template strips ".tmpl" when
    # WRITING, but status compares against the un-stripped path, so we do too.)
    return os.path.join(home, item.path)


def _read_text(path):
    # type: (str) -> str
    with open(path, "r") as fh:
        return fh.read()


def _unified(expected, live, path):
    # type: (str, str, str) -> str
    # difflib wants line lists; keepends so multi-line bodies render naturally.
    expected_lines = expected.splitlines(keepends=True)
    live_lines = live.splitlines(keepends=True)
    diff = difflib.unified_diff(
        expected_lines,
        live_lines,
        fromfile="expected:" + path,
        tofile="live:" + path,
    )
    return "".join(diff)


def compute(root, home, os_name, only=None):
    # type: (str, str, str, Optional[str]) -> List[Tuple[str, str, str]]
    """For each base manifest item applicable to os_name (optionally filtered to
    `only` == an item path), return (path, status, diff_text):
      status in {"ok","drift","missing"};
      diff_text is a difflib unified diff (expected -> live), "" when ok.
    `only` may be the manifest path (e.g. 'agents/debugger.md'); raise ValueError
    if `only` matches no item."""
    items = manifest.parse(config.manifest_path(root))
    src_base = config.home_claude_src(root)
    env = localenv.load(config.localenv_path(root))
    vars_ = localenv.template_vars(env)
    vault = _vault_enabled(env)

    results = []  # type: List[Tuple[str, str, str]]
    matched = False
    for item in items:
        if not manifest.applies_to_os(item, os_name):
            continue
        if item.layer != "base":
            continue
        if only is not None and item.path != only:
            continue
        matched = True

        src = os.path.join(src_base, item.path)
        target = _live_target(home, item)

        # Missing live file => "missing": the whole expected body is "added".
        # A directory source (e.g. a skill dir) has no single-file content to
        # diff, so emit an empty diff body — same spirit as _compute_drift, which
        # never content-compares a directory source.
        if not os.path.exists(target):
            if os.path.isdir(src):
                results.append((item.path, "missing", ""))
            else:
                expected = _build_expected(item, src, target, vars_, vault)
                results.append(
                    (item.path, "missing", _unified(expected, "", item.path))
                )
            continue

        # Mirror _compute_drift: a directory source or a live symlink is treated
        # as "ok" without a content comparison (symlinks track the source by
        # definition; directories are not single-file content).
        if os.path.isdir(src) or os.path.islink(target):
            results.append((item.path, "ok", ""))
            continue

        try:
            expected = _build_expected(item, src, target, vars_, vault)
            live = _read_text(target)
        except OSError:
            # Same fallthrough as _compute_drift: unreadable => report drift. No
            # text to diff, so diff_text stays empty.
            results.append((item.path, "drift", ""))
            continue

        if expected == live:
            results.append((item.path, "ok", ""))
        else:
            results.append(
                (item.path, "drift", _unified(expected, live, item.path))
            )

    if only is not None and not matched:
        raise ValueError("no base manifest item matches {0!r}".format(only))
    return results


def _build_expected(item, src, target, vars_, vault_enabled):
    # type: (manifest.Item, str, str, Dict[str, str], bool) -> str
    # Render the "expected" content for the diff. Kept separate from
    # _expected_content because `merge` needs the live target path (to merge onto
    # the current live file, exactly like apply.apply_merge_json -> mergejson).
    if item.mode == "merge":
        with open(src, "r") as fh:
            base_obj = json.load(fh)
        merged = mergejson.merge_settings_file(target, base_obj)
        return json.dumps(merged, indent=2)
    if item.mode == "template":
        raw = _read_text(src)
        return template.render(raw, vars_, vault_enabled)
    # symlink (and any future raw mode): the source file's content verbatim.
    return _read_text(src)


def render(results, only=None):
    # type: (List[Tuple[str, str, str]], Optional[str]) -> str
    """Human output: a unified diff per drifted/missing item + a summary line
    'N ok · M drift · K missing'. When everything is ok, a clean message."""
    ok = drift = missing = 0
    blocks = []  # type: List[str]
    for path, status, diff_text in results:
        if status == "ok":
            ok += 1
            continue
        if status == "drift":
            drift += 1
        elif status == "missing":
            missing += 1
        header = "{0}\t{1}".format(path, status)
        if diff_text:
            blocks.append(header + "\n" + diff_text.rstrip("\n"))
        else:
            blocks.append(header)

    summary = "{0} ok · {1} drift · {2} missing".format(ok, drift, missing)

    if not blocks:
        # Everything compared clean (within whatever filter was applied).
        scope = " for {0}".format(only) if only is not None else ""
        return "no content drift{0} — {1}".format(scope, summary)

    return "\n\n".join(blocks) + "\n\n" + summary
