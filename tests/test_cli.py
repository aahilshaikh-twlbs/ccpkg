import json
import os
import subprocess
import sys

import pytest

from ccpkg import cli
from ccpkg import installer
from ccpkg import push as push_mod


def _seed_localenv(repo, home):
    # minimal local.env so localenv.load resolves cleanly; HOME-only template vars.
    with open(os.path.join(repo, "local.env"), "w") as fh:
        fh.write("CODE_ROOT=$HOME/Documents/Code\n")
        fh.write("VAULT_ROOT=\n")
        fh.write("AWS_PROFILE=\n")
        fh.write("OVERLAY_REPO=\n")
        fh.write("OVERLAY_DIR=\n")


def _patch_resolution(monkeypatch, repo, home):
    # cli.main resolves root/home/env via config; redirect both to the fixtures.
    monkeypatch.setattr(cli.config, "repo_root", lambda: repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: home)


def _seed_purity_terms(repo, *terms):
    # write a local .ccpkg/purity-terms.txt with placeholder terms the scan loads.
    ccpkg_dir = os.path.join(repo, ".ccpkg")
    os.makedirs(ccpkg_dir, exist_ok=True)
    with open(os.path.join(ccpkg_dir, "purity-terms.txt"), "w") as fh:
        fh.write("\n".join(terms) + "\n")


def test_main_scan_exits_1_on_planted_purity(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    _seed_purity_terms(tmp_repo, "acmecorp")
    # plant a purity term in a base source file under home/.claude.
    base_src = os.path.join(tmp_repo, "home", ".claude")
    planted = os.path.join(base_src, "settings.json")
    with open(planted, "w") as fh:
        fh.write('{"company": "acmecorp"}\n')

    rc = cli.main(["scan"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "acmecorp" in out
    assert "purity" in out


def test_main_scan_is_repo_wide(tmp_repo, tmp_home, monkeypatch, capsys):
    # the scan must sweep the whole repo, not just home/.claude — a planted term
    # in a top-level shippable file is caught.
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    _seed_purity_terms(tmp_repo, "acmecorp")
    with open(os.path.join(tmp_repo, "README.md"), "w") as fh:
        fh.write("we partnered with acmecorp last year\n")

    rc = cli.main(["scan"])

    assert rc == 1
    out = capsys.readouterr().out
    assert "acmecorp" in out
    assert "README.md" in out


def test_main_scan_clean_exits_0(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    _seed_purity_terms(tmp_repo, "acmecorp")
    # overwrite any seeded base file with clean content.
    base_src = os.path.join(tmp_repo, "home", ".claude")
    with open(os.path.join(base_src, "settings.json"), "w") as fh:
        fh.write('{"model": "opus"}\n')

    rc = cli.main(["scan"])

    assert rc == 0


def test_main_pull_applies_items(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    # ensure the base settings.json source is clean and present.
    base_src = os.path.join(tmp_repo, "home", ".claude")
    with open(os.path.join(base_src, "settings.json"), "w") as fh:
        fh.write('{"model": "opus"}\n')

    rc = cli.main(["pull"])

    assert rc == 0
    # pull applies the manifest items into home_target.
    applied = os.path.join(tmp_home, "settings.json")
    assert os.path.exists(applied)
    out = capsys.readouterr().out
    assert "settings.json" in out


def test_main_pull_does_not_install_deps_or_plugins(tmp_repo, tmp_home, monkeypatch):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    with open(os.path.join(tmp_repo, "home", ".claude", "settings.json"), "w") as fh:
        fh.write('{"model": "opus"}\n')
    called = {"install": False}

    def _boom(*a, **k):
        called["install"] = True
        raise AssertionError("installer.install must not run on pull")

    monkeypatch.setattr(cli.installer, "install", _boom)

    rc = cli.main(["pull"])

    assert rc == 0
    assert called["install"] is False


def test_main_install_invokes_installer_and_prints_report(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    captured = {}

    def _fake_install(root, home_target, env, os_name, run=subprocess.run, interactive=False):
        captured["root"] = root
        captured["home_target"] = home_target
        captured["os_name"] = os_name
        return installer.InstallReport(
            os=os_name, deps={"git": "present"},
            base_applied=[("settings.json", "linked")],
            overlay_applied=[], plugins={}, mailbox={}, scan_findings=[], notes=[],
        )

    monkeypatch.setattr(cli.installer, "install", _fake_install)

    rc = cli.main(["install"])

    assert rc == 0
    assert captured["root"] == tmp_repo
    assert captured["home_target"] == tmp_home
    out = capsys.readouterr().out
    assert "settings.json" in out
    assert "linked" in out


def test_main_push_invokes_push_and_prints_summary(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    captured = {}

    def _fake_push(root, home_target, env, paths, confirm=None, os_name="darwin"):
        captured["paths"] = paths
        return {"written": ["settings.json"], "skipped": [], "blocked": []}

    monkeypatch.setattr(cli.push, "push", _fake_push)

    rc = cli.main(["push", "settings.json"])

    assert rc == 0
    assert captured["paths"] == ["settings.json"]
    out = capsys.readouterr().out
    assert "written" in out
    assert "settings.json" in out


def test_main_status_prints_drift(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    # base source differs from (absent) live target -> drift expected.
    with open(os.path.join(tmp_repo, "home", ".claude", "settings.json"), "w") as fh:
        fh.write('{"model": "opus"}\n')

    rc = cli.main(["status"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "settings.json" in out
    # absent live target reported as drift.
    assert "missing" in out


def test_main_doctor_prints_drift(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    with open(os.path.join(tmp_repo, "home", ".claude", "settings.json"), "w") as fh:
        fh.write('{"model": "opus"}\n')

    rc = cli.main(["doctor"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "settings.json" in out


def test_main_unknown_subcommand_nonzero(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)

    # argparse exits with SystemExit(2) on an invalid choice.
    with pytest.raises(SystemExit) as exc:
        cli.main(["bogus"])

    assert exc.value.code != 0


def test_main_no_subcommand_prints_help_nonzero(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)

    rc = cli.main([])

    assert rc != 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_dunder_main_calls_sys_exit(tmp_repo, tmp_home, monkeypatch):
    # python3 -m ccpkg with no args -> nonzero exit via sys.exit(main()).
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(cli.__file__)))
    proc = subprocess.run(
        [sys.executable, "-m", "ccpkg"],
        env=env, capture_output=True, text=True,
    )
    assert proc.returncode != 0
