import json
import os

import pytest

from ccpkg import cli, config, gallery, share

REAL_ROOT = config.repo_root()
SHIPPED = {"minimalist", "full-stack", "ai-researcher"}


def _seed_localenv(repo):
    with open(os.path.join(repo, "local.env"), "w") as fh:
        fh.write("OVERLAY_REPO=\nOVERLAY_DIR=\nVAULT_ROOT=\n")


# --- shipped entries validate against the real catalog -----------------------

def test_ships_seed_entries():
    names = {e["name"] for e in gallery.list_entries(REAL_ROOT)}
    assert SHIPPED <= names


def test_entries_are_ranked_by_score():
    entries = gallery.list_entries(REAL_ROOT)
    scores = [e["score"] for e in entries]
    assert scores == sorted(scores, reverse=True)


def test_every_entry_id_in_catalog():
    catalog = set(share._catalog(REAL_ROOT, False))
    for path in gallery._entry_files(REAL_ROOT):
        data = json.load(open(path))
        missing = [s for s in data["selected"] if s not in catalog]
        assert not missing, "%s references non-catalog ids: %s" % (path, missing)


def test_entries_are_scan_clean():
    from ccpkg import scan
    terms = scan.load_purity_terms(REAL_ROOT)
    for path in gallery._entry_files(REAL_ROOT):
        text = open(path, encoding="utf-8").read()
        assert not scan.scan_text_purity(text, terms, path)
        assert not scan.scan_text_secrets(text, path)


# --- index rendering ---------------------------------------------------------

def test_render_index_is_markdown_table():
    md = gallery.render_index(REAL_ROOT)
    assert "# ccpkg setup gallery" in md
    assert "| Setup | By | Score |" in md
    for name in SHIPPED:
        assert name in md
    assert "ccpkg apply gallery/" in md


def test_render_index_empty_dir(tmp_path):
    md = gallery.render_index(str(tmp_path))
    assert "no entries yet" in md


def test_write_index_writes_file(tmp_path, monkeypatch):
    # build a tiny gallery in a temp root
    gdir = tmp_path / "gallery"
    gdir.mkdir()
    (gdir / "x.share.json").write_text(json.dumps(
        {"ccpkg_share": 1, "name": "x", "selected": ["mboard"]}))
    monkeypatch.setattr(gallery.share_mod, "_catalog",
                        lambda root, ov: {"mboard": ("Coordination", "")})
    path = gallery.write_index(str(tmp_path))
    assert os.path.exists(path)
    assert os.path.basename(path) == "GALLERY.md"


# --- the committed GALLERY.md is in sync (so the repo's index never goes stale)

def test_committed_index_is_current():
    committed_path = os.path.join(REAL_ROOT, gallery.INDEX_FILENAME)
    assert os.path.exists(committed_path), "GALLERY.md missing — run `ccpkg gallery index`"
    committed = open(committed_path, encoding="utf-8").read()
    assert committed == gallery.render_index(REAL_ROOT), \
        "GALLERY.md is stale — run `ccpkg gallery index` and commit"


# --- CLI ---------------------------------------------------------------------

def test_cli_gallery_lists(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo)
    monkeypatch.setattr(cli.config, "repo_root", lambda: REAL_ROOT)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    rc = cli.main(["gallery"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Community setups" in out
    assert "adopt: ccpkg apply gallery/" in out


def test_cli_gallery_index_writes(tmp_home, monkeypatch, capsys, tmp_path):
    # point repo_root at a temp root with a gallery, so we don't rewrite the real one
    groot = tmp_path
    gdir = groot / "gallery"
    gdir.mkdir()
    (gdir / "y.share.json").write_text(json.dumps(
        {"ccpkg_share": 1, "name": "y", "selected": ["mboard"]}))
    monkeypatch.setattr(cli.config, "repo_root", lambda: str(groot))
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(gallery.share_mod, "_catalog",
                        lambda root, ov: {"mboard": ("Coordination", "")})
    rc = cli.main(["gallery", "index"])
    assert rc == 0
    assert os.path.exists(str(groot / "GALLERY.md"))
