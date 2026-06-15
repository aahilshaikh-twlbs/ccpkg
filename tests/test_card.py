import os
from xml.dom import minidom

import pytest

from ccpkg import card, cli, config, share

REAL_ROOT = config.repo_root()


def _seed_localenv(repo):
    with open(os.path.join(repo, "local.env"), "w") as fh:
        fh.write("OVERLAY_REPO=\nOVERLAY_DIR=\nVAULT_ROOT=\n")


# --- render_svg --------------------------------------------------------------

def _sample_stats():
    return {"score": 84, "grade": "B", "total": 30,
            "groups": {"Agents": 12, "Plugins": 2, "Skills": 1, "Commands": 1},
            "mboard": True}


def test_render_svg_is_well_formed_xml():
    svg = card.render_svg(_sample_stats())
    doc = minidom.parseString(svg)        # raises if malformed
    assert doc.documentElement.tagName == "svg"


def test_render_svg_includes_score_and_grade():
    svg = card.render_svg(_sample_stats())
    assert "84/100" in svg
    assert ">B<" in svg
    assert "Agents" in svg


def test_render_svg_escapes_title():
    svg = card.render_svg(_sample_stats(), title="a <b> & c")
    minidom.parseString(svg)              # must stay valid XML
    assert "<b>" not in svg.split("aria-label")[1][:40] or "&lt;b&gt;" in svg


def test_render_svg_unknown_grade_color_falls_back():
    svg = card.render_svg({"score": 0, "grade": "?", "total": 0, "groups": {}, "mboard": False})
    minidom.parseString(svg)


def test_build_stats(tmp_repo, tmp_home, monkeypatch):
    monkeypatch.setattr(config, "repo_root", lambda: tmp_repo)
    stats = card.build_stats(tmp_repo, tmp_home, False)
    assert "score" in stats and "grade" in stats
    assert isinstance(stats["groups"], dict)


def test_card_module_is_scan_clean():
    from ccpkg import scan
    src = os.path.join(REAL_ROOT, "ccpkg", "card.py")
    text = open(src, encoding="utf-8").read()
    terms = scan.load_purity_terms(REAL_ROOT)
    assert not scan.scan_text_secrets(text, src)
    assert not scan.scan_text_purity(text, terms, src)


# --- CLI ---------------------------------------------------------------------

def test_cli_card_writes_svg(tmp_repo, tmp_home, tmp_path, monkeypatch, capsys):
    _seed_localenv(tmp_repo)
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    out = str(tmp_path / "mycard.svg")
    rc = cli.main(["card", out])
    assert rc == 0
    assert os.path.exists(out)
    minidom.parseString(open(out).read())   # valid SVG on disk
    assert "wrote" in capsys.readouterr().out
