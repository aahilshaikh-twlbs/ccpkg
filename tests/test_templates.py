import json
import os

import pytest

from ccpkg import cli, config, installer, profile, share, templates

# The shipped templates are validated against the REAL repo catalog (the whole
# point of the test: a template id that drifts out of the catalog must fail CI).
REAL_ROOT = config.repo_root()
SHIPPED = ["web-dev", "backend", "research", "the-works"]


def _seed_localenv(repo):
    with open(os.path.join(repo, "local.env"), "w") as fh:
        fh.write("OVERLAY_REPO=\nOVERLAY_DIR=\nVAULT_ROOT=\n")


# --- shipped templates validate against the real catalog ---------------------

def test_ships_expected_templates():
    assert set(templates.list_templates(REAL_ROOT)) == set(SHIPPED)


@pytest.mark.parametrize("name", SHIPPED)
def test_template_parses_and_every_id_in_catalog(name):
    data = templates.resolve_template(name, REAL_ROOT)
    assert data is not None
    assert data["ccpkg_share"] == share.SHARE_SCHEMA
    selected = data["selected"]
    assert selected, "%s has no selected ids" % name
    assert len(selected) == len(set(selected)), "%s has duplicate ids" % name
    catalog = set(share._catalog(REAL_ROOT, False).keys())
    missing = [s for s in selected if s not in catalog]
    assert not missing, "%s references ids not in the catalog: %s" % (name, missing)


def test_the_works_is_the_whole_catalog():
    data = templates.resolve_template("the-works", REAL_ROOT)
    catalog = set(share._catalog(REAL_ROOT, False).keys())
    assert set(data["selected"]) == catalog


def test_templates_are_scan_clean():
    # the template JSON files live under templates/ (scanned); confirm pure.
    from ccpkg import scan
    terms = scan.load_purity_terms(REAL_ROOT)
    for name in SHIPPED:
        path = templates.template_path(name, REAL_ROOT)
        text = open(path, encoding="utf-8").read()
        assert not scan.scan_text_purity(text, terms, path)


# --- resolve_template behavior -----------------------------------------------

def test_resolve_unknown_template_is_none():
    assert templates.resolve_template("does-not-exist", REAL_ROOT) is None


def test_list_templates_missing_dir(tmp_path):
    assert templates.list_templates(str(tmp_path)) == []


# --- apply dispatch: a template name routes to the adopt path ----------------

def test_apply_template_name_adopts(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo)
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    # ship a template in tmp_repo whose ids exist in tmp_repo's tiny catalog
    tdir = os.path.join(tmp_repo, "templates", "tiny")
    os.makedirs(tdir)
    with open(os.path.join(tdir, share.SHARE_FILENAME), "w") as fh:
        json.dump({"ccpkg_share": 1, "name": "tiny",
                   "description": "tiny test template",
                   "selected": ["settings.json"], "deselected": []}, fh)
    captured = {}

    def _fake_install(root, home_target, env, os_name, run=None, selected=None):
        captured["selected"] = selected
        return installer.InstallReport(os=os_name)

    monkeypatch.setattr(cli.installer, "install", _fake_install)

    rc = cli.main(["apply", "tiny"])   # non-TTY under pytest -> no confirm

    assert rc == 0
    assert captured["selected"] == {"settings.json"}
    out = capsys.readouterr().out
    assert "Starter template: tiny" in out
    assert "tiny test template" in out
    saved = profile.load(tmp_home)
    assert saved is not None and "settings.json" in saved.selected


def test_apply_unknown_source_falls_through_to_share(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo)
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    # not a preset, not a template, not a valid path/URL -> share fetch -> rc 2
    rc = cli.main(["apply", os.path.join(tmp_home, "nope-not-a-share")])
    assert rc == 2
    assert "ccpkg apply" in capsys.readouterr().err


# --- the completions templates feed ------------------------------------------

def test_completions_templates_feed(monkeypatch, capsys):
    monkeypatch.setattr(cli.config, "repo_root", lambda: REAL_ROOT)
    rc = cli.main(["completions", "templates"])
    assert rc == 0
    names = [ln for ln in capsys.readouterr().out.splitlines() if ln]
    assert set(names) == set(SHIPPED)
