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

    def _fake_install(root, home_target, env, os_name, run=subprocess.run,
                      interactive=False, selected=None):
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


def test_install_parser_accepts_new_flags():
    from ccpkg import cli
    parser = cli._build_parser()
    args = parser.parse_args(["install", "--yes"])
    assert args.yes is True
    args = parser.parse_args(["install", "--reconfigure"])
    assert args.reconfigure is True
    args = parser.parse_args(["install", "--non-interactive"])
    assert args.yes is True            # --non-interactive aliases --yes


def _stub_install(*a, **k):
    # A fast installer.install double: a valid empty InstallReport, no side effects.
    return installer.InstallReport(
        os="darwin", deps={}, base_applied=[], overlay_applied=[],
        plugins={}, mailbox={}, scan_findings=[], notes=[],
    )


def test_install_yes_is_headless_and_writes_no_profile(tmp_repo, tmp_home, monkeypatch):
    from ccpkg import cli, profile
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    # --yes with NO prior profile applies defaults headlessly; the wizard never
    # ran, so NO profile is persisted (the wizard owns the profile).
    rc = cli.main(["install", "--yes"])
    assert rc == 0
    assert profile.load(tmp_home) is None


def test_install_wizard_path_writes_profile(tmp_repo, tmp_home, monkeypatch):
    from ccpkg import cli, profile, wizard
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(wizard, "run_wizard", lambda stages, pre: {"settings.json"})
    monkeypatch.setattr(installer, "install", _stub_install)

    rc = cli.main(["install"])           # interactive TTY path, no prior profile
    assert rc == 0
    prof = profile.load(tmp_home)
    assert prof is not None
    assert prof.selected == ["settings.json"]


def test_install_reconfigure_writes_profile(tmp_repo, tmp_home, monkeypatch):
    from ccpkg import cli, profile, wizard
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    profile.save(tmp_home, profile.Profile(selected=["settings.json"], deselected=[]))
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(wizard, "run_wizard",
                        lambda stages, pre: {"settings.json", "statusline.sh"})
    monkeypatch.setattr(installer, "install", _stub_install)

    rc = cli.main(["install", "--reconfigure"])
    assert rc == 0
    prof = profile.load(tmp_home)
    assert set(prof.selected) == {"settings.json", "statusline.sh"}


def test_install_replay_does_not_rewrite_profile(tmp_repo, tmp_home, monkeypatch):
    from ccpkg import cli, profile
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    profile.save(tmp_home, profile.Profile(selected=["settings.json"],
                                           deselected=["statusline.sh"]))
    monkeypatch.setattr(installer, "install", _stub_install)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)

    saved = {"called": False}
    monkeypatch.setattr(profile, "save",
                        lambda *a, **k: saved.__setitem__("called", True))

    rc = cli.main(["install"])           # profile present, not reconfigure -> replay
    assert rc == 0
    assert saved["called"] is False      # replay must NOT rewrite the profile


def test_install_ctrl_c_during_wizard_cancels(tmp_repo, tmp_home, monkeypatch, capsys):
    from ccpkg import cli, wizard
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)

    def _boom(stages, pre):
        raise KeyboardInterrupt

    monkeypatch.setattr(wizard, "run_wizard", _boom)

    def _no_install(*a, **k):
        raise AssertionError("installer.install must not run after Ctrl-C")

    monkeypatch.setattr(installer, "install", _no_install)

    rc = cli.main(["install"])
    assert rc == 130
    assert "cancelled" in capsys.readouterr().out.lower()


def test_dunder_main_calls_sys_exit(tmp_repo, tmp_home, monkeypatch):
    # python3 -m ccpkg with no args -> nonzero exit via sys.exit(main()).
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(cli.__file__)))
    proc = subprocess.run(
        [sys.executable, "-m", "ccpkg"],
        env=env, capture_output=True, text=True,
    )
    assert proc.returncode != 0
