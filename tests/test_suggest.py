import json
import os

import pytest

from ccpkg import cli, config, installer, mcp, share, suggest

REAL_ROOT = config.repo_root()


def _seed_localenv(repo):
    with open(os.path.join(repo, "local.env"), "w") as fh:
        fh.write("OVERLAY_REPO=\nOVERLAY_DIR=\nVAULT_ROOT=\n")


# --- detect ------------------------------------------------------------------

def test_detect_rust(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n")
    (tmp_path / "main.rs").write_text("fn main() {}")
    signals = suggest.detect(str(tmp_path))
    assert "rust" in signals


def test_detect_node_frontend(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18"}}))
    signals = suggest.detect(str(tmp_path))
    assert "node" in signals
    assert "frontend" in signals


def test_detect_docker_and_db(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    (tmp_path / "schema.prisma").write_text("// schema")
    signals = suggest.detect(str(tmp_path))
    assert "docker" in signals
    assert "database" in signals


def test_detect_empty_project_is_empty(tmp_path):
    assert suggest.detect(str(tmp_path)) == set()


def test_detect_never_raises_on_missing_dir():
    assert suggest.detect("/nonexistent/path/xyz") == set()


# --- recommend ---------------------------------------------------------------

def test_recommend_always_includes_base():
    catalog = set(share._catalog(REAL_ROOT, False))
    selected, mcp_ids, rationale = suggest.recommend(set(), catalog)
    assert "agents/reviewer.md" in selected
    assert "superpowers" in selected
    assert "git" in mcp_ids


def test_recommend_frontend_adds_frontend_agents():
    catalog = set(share._catalog(REAL_ROOT, False))
    selected, _mcp, _r = suggest.recommend({"frontend"}, catalog)
    assert "agents/frontend.md" in selected
    assert "frontend-design" in selected


def test_recommend_database_adds_dba_and_mcp():
    catalog = set(share._catalog(REAL_ROOT, False))
    selected, mcp_ids, _r = suggest.recommend({"database"}, catalog)
    assert "agents/dba.md" in selected
    assert "postgres" in mcp_ids


def test_recommend_is_sorted_deduped_and_rationale_complete():
    catalog = set(share._catalog(REAL_ROOT, False))
    selected, _mcp, rationale = suggest.recommend({"rust", "docker", "github"}, catalog)
    assert selected == sorted(set(selected))
    assert {r["id"] for r in rationale} == set(selected)
    assert all(r["why"] for r in rationale)


def test_every_rule_id_exists_in_catalog():
    # drift guard: every id any rule can emit must be a real catalog id
    catalog = set(share._catalog(REAL_ROOT, False))
    rule_ids = set(suggest._BASE_IDS)
    for ids, _mcp, _why in suggest.SIGNAL_RULES.values():
        rule_ids.update(ids)
    missing = [i for i in rule_ids if i not in catalog]
    assert not missing, "suggest rules reference non-catalog ids: %s" % missing


def test_every_rule_mcp_exists_in_catalog():
    mcp_catalog = set(mcp.catalog_ids())
    rule_mcp = set(suggest._BASE_MCP)
    for _ids, mcp_ids, _why in suggest.SIGNAL_RULES.values():
        rule_mcp.update(mcp_ids)
    missing = [m for m in rule_mcp if m not in mcp_catalog]
    assert not missing, "suggest rules reference non-catalog MCP ids: %s" % missing


def test_suggest_module_is_scan_clean():
    from ccpkg import scan
    src = os.path.join(REAL_ROOT, "ccpkg", "suggest.py")
    text = open(src, encoding="utf-8").read()
    terms = scan.load_purity_terms(REAL_ROOT)
    assert not scan.scan_text_secrets(text, src)
    assert not scan.scan_text_purity(text, terms, src)


# --- CLI ---------------------------------------------------------------------

def test_cli_suggest_preview_changes_nothing(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo)
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    proj = tmp_repo  # use the repo dir as the "project" cwd
    monkeypatch.chdir(proj)

    def _no_install(*a, **k):
        raise AssertionError("preview must not install")
    monkeypatch.setattr(cli.installer, "install", _no_install)

    rc = cli.main(["suggest", "preview"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Recommended setup" in out
    assert "preview only" in out
    assert not os.path.exists(os.path.join(proj, ".mcp.json"))


def test_cli_suggest_applies(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo)
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.chdir(tmp_repo)
    captured = {}

    def _fake_install(root, home_target, env, os_name, run=None, selected=None):
        captured["selected"] = selected
        return installer.InstallReport(os=os_name)

    monkeypatch.setattr(cli.installer, "install", _fake_install)

    # tmp_repo's catalog only has settings.json etc.; recommend intersects with it.
    rc = cli.main(["suggest"])
    assert rc == 0
    assert "selected" in captured            # install ran (auto-apply, no prompt)
    out = capsys.readouterr().out
    assert "configured Claude Code" in out
