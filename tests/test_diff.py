"""Tests for ccpkg.diff — content diff between repo-managed files and live ~/.claude.

Uses the REAL repo root (Path(__file__).parents[1]) so the manifest + base
source-of-truth are the actual shipped files, and a tmp_path `home` whose live
files we construct per case. `diff.compute` must agree with the drift semantics
in cli._compute_drift while additionally producing a unified diff body.
"""

import os
from pathlib import Path

import pytest

from ccpkg import diff

REPO_ROOT = str(Path(__file__).resolve().parents[1])
# A stable base symlink item that exists in the shipped manifest + source tree.
SYMLINK_ITEM = "agents/debugger.md"


def _src_path(item_path):
    # type: (str) -> str
    return os.path.join(REPO_ROOT, "home", ".claude", item_path)


def _result_for(results, item_path):
    for path, status, diff_text in results:
        if path == item_path:
            return (path, status, diff_text)
    raise AssertionError("no result for {0}".format(item_path))


def test_missing_live_file_is_missing_with_diff(tmp_path):
    # No live file at home/<item> => status "missing"; the whole expected body is
    # rendered as added, so diff_text must be non-empty.
    home = str(tmp_path / "home")
    os.makedirs(home)
    results = diff.compute(REPO_ROOT, home, "darwin", only=SYMLINK_ITEM)
    assert len(results) == 1
    path, status, diff_text = results[0]
    assert path == SYMLINK_ITEM
    assert status == "missing"
    assert diff_text != ""
    assert SYMLINK_ITEM in diff_text


def test_identical_live_copy_is_ok_no_diff(tmp_path):
    # A live regular file whose content equals the source => "ok", empty diff.
    home = str(tmp_path / "home")
    target = os.path.join(home, SYMLINK_ITEM)
    os.makedirs(os.path.dirname(target))
    with open(_src_path(SYMLINK_ITEM)) as fh:
        src_text = fh.read()
    with open(target, "w") as fh:
        fh.write(src_text)

    results = diff.compute(REPO_ROOT, home, "darwin", only=SYMLINK_ITEM)
    assert len(results) == 1
    path, status, diff_text = results[0]
    assert status == "ok"
    assert diff_text == ""


def test_differing_live_file_is_drift_with_hunk(tmp_path):
    # A live file that differs from the source => "drift"; diff_text carries a
    # +/- hunk and names the path.
    home = str(tmp_path / "home")
    target = os.path.join(home, SYMLINK_ITEM)
    os.makedirs(os.path.dirname(target))
    with open(_src_path(SYMLINK_ITEM)) as fh:
        src_text = fh.read()
    with open(target, "w") as fh:
        fh.write(src_text + "\nLOCAL EDIT THAT IS NOT IN THE SOURCE\n")

    results = diff.compute(REPO_ROOT, home, "darwin", only=SYMLINK_ITEM)
    assert len(results) == 1
    path, status, diff_text = results[0]
    assert status == "drift"
    assert SYMLINK_ITEM in diff_text
    assert any(line.startswith("+") for line in diff_text.splitlines())
    assert any(line.startswith("-") or line.startswith("@@")
               for line in diff_text.splitlines())
    assert "LOCAL EDIT THAT IS NOT IN THE SOURCE" in diff_text


def test_only_filters_to_one_item(tmp_path):
    home = str(tmp_path / "home")
    os.makedirs(home)
    results = diff.compute(REPO_ROOT, home, "darwin", only=SYMLINK_ITEM)
    assert len(results) == 1
    assert results[0][0] == SYMLINK_ITEM


def test_only_unknown_item_raises(tmp_path):
    home = str(tmp_path / "home")
    os.makedirs(home)
    with pytest.raises(ValueError):
        diff.compute(REPO_ROOT, home, "darwin", only="nope/x.md")


def test_compute_without_only_covers_many_base_items(tmp_path):
    # Sanity: no filter returns every applicable base item (more than one), and
    # an absent live home means they're all "missing".
    home = str(tmp_path / "home")
    os.makedirs(home)
    results = diff.compute(REPO_ROOT, home, "darwin")
    assert len(results) > 1
    statuses = {status for _p, status, _d in results}
    assert statuses == {"missing"}


def test_render_clean_shows_summary_when_all_ok(tmp_path):
    # Build a live tree identical to source for a single item; render reports a
    # clean message containing the 'ok ·' summary counts.
    home = str(tmp_path / "home")
    target = os.path.join(home, SYMLINK_ITEM)
    os.makedirs(os.path.dirname(target))
    with open(_src_path(SYMLINK_ITEM)) as fh:
        src_text = fh.read()
    with open(target, "w") as fh:
        fh.write(src_text)

    results = diff.compute(REPO_ROOT, home, "darwin", only=SYMLINK_ITEM)
    out = diff.render(results, only=SYMLINK_ITEM)
    assert "ok ·" in out
    assert "1 ok · 0 drift · 0 missing" in out


def test_render_drift_shows_diff_markers_and_summary(tmp_path):
    home = str(tmp_path / "home")
    target = os.path.join(home, SYMLINK_ITEM)
    os.makedirs(os.path.dirname(target))
    with open(_src_path(SYMLINK_ITEM)) as fh:
        src_text = fh.read()
    with open(target, "w") as fh:
        fh.write(src_text + "\nLOCAL EDIT\n")

    results = diff.compute(REPO_ROOT, home, "darwin", only=SYMLINK_ITEM)
    out = diff.render(results, only=SYMLINK_ITEM)
    # unified-diff markers present
    assert "--- expected:" in out
    assert "+++ live:" in out
    assert "@@" in out
    assert "+LOCAL EDIT" in out
    # summary line with drift counted
    assert "ok ·" in out
    assert "1 drift" in out
