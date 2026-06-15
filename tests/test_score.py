import os

import pytest

from ccpkg import cli, config, score, share

REAL_ROOT = config.repo_root()


def _seed_localenv(repo):
    with open(os.path.join(repo, "local.env"), "w") as fh:
        fh.write("OVERLAY_REPO=\nOVERLAY_DIR=\nVAULT_ROOT=\n")


# --- pure scoring ------------------------------------------------------------

def test_grade_bands():
    assert score.grade_for(100) == "A"
    assert score.grade_for(90) == "A"
    assert score.grade_for(85) == "B"
    assert score.grade_for(72) == "C"
    assert score.grade_for(61) == "D"
    assert score.grade_for(10) == "F"


def test_empty_selection_scores_zero():
    catalog = share._catalog(REAL_ROOT, False)
    r = score.analyze(set(), catalog)
    assert r.score == 0
    assert r.grade == "F"
    assert r.suggestions          # an empty setup should have suggestions


def test_full_catalog_scores_high():
    catalog = share._catalog(REAL_ROOT, False)
    r = score.analyze(set(catalog), catalog)
    assert r.score >= 90
    assert r.grade == "A"
    # dimension maxima sum to 100
    assert sum(mx for _n, _g, mx in r.dimensions) == 100


def test_score_never_exceeds_100_or_below_0():
    catalog = share._catalog(REAL_ROOT, False)
    for sel in (set(), {"mboard"}, set(catalog), {"agents/reviewer.md"}):
        r = score.analyze(sel, catalog)
        assert 0 <= r.score <= 100


def test_key_agents_drive_core_loop_dimension():
    catalog = share._catalog(REAL_ROOT, False)
    r = score.analyze(set(score.KEY_AGENTS), catalog)
    core = [d for d in r.dimensions if d[0] == "Core review loop"][0]
    assert core[1] == core[2]   # all five key agents -> full points for the dim
    assert "full core review loop" in " ".join(r.strengths)


def test_mboard_strength_and_suggestion():
    catalog = share._catalog(REAL_ROOT, False)
    with_mb = score.analyze({"mboard"}, catalog)
    assert "mboard coordination enabled" in with_mb.strengths
    without_mb = score.analyze({"agents/reviewer.md"}, catalog)
    assert any("mboard" in s for s in without_mb.suggestions)


def test_key_agents_all_in_catalog():
    catalog = set(share._catalog(REAL_ROOT, False))
    missing = [a for a in score.KEY_AGENTS if a not in catalog]
    assert not missing, "KEY_AGENTS not in catalog: %s" % missing


# --- CLI ---------------------------------------------------------------------

def test_cli_score_runs(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo)
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    rc = cli.main(["score"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "/ 100" in out
    assert "Agent breadth" in out
