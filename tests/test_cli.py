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

    rc = cli.main(["status", "scan"])

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

    rc = cli.main(["status", "scan"])

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

    rc = cli.main(["status", "scan"])

    assert rc == 0


def test_main_apply_invokes_installer_and_prints_report(tmp_repo, tmp_home, monkeypatch, capsys):
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
            overlay_applied=[], plugins={}, mboard={}, scan_findings=[], notes=[],
        )

    monkeypatch.setattr(cli.installer, "install", _fake_install)

    rc = cli.main(["apply"])

    assert rc == 0
    assert captured["root"] == tmp_repo
    assert captured["home_target"] == tmp_home
    out = capsys.readouterr().out
    assert "settings.json" in out
    assert "linked" in out


def test_main_push_invokes_push_and_prints_summary(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    monkeypatch.delenv("CCPKG_ROOT", raising=False)
    os.makedirs(os.path.join(tmp_repo, ".git"), exist_ok=True)  # looks like a checkout
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


def test_push_blocked_when_packaged(monkeypatch, tmp_path, capsys):
    from ccpkg import cli, config
    monkeypatch.setattr(config, "repo_root", lambda: str(tmp_path))
    monkeypatch.setattr(config, "home_target", lambda: str(tmp_path))
    monkeypatch.setenv("CCPKG_ROOT", str(tmp_path))  # packaged, no .git
    rc = cli.main(["push"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "git checkout" in err


def test_push_blocked_when_no_git_checkout(monkeypatch, tmp_path, capsys):
    from ccpkg import cli, config
    monkeypatch.delenv("CCPKG_ROOT", raising=False)
    monkeypatch.setattr(config, "repo_root", lambda: str(tmp_path))  # no .git dir
    monkeypatch.setattr(config, "home_target", lambda: str(tmp_path))
    rc = cli.main(["push"])
    assert rc == 2
    assert "git checkout" in capsys.readouterr().err


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


def test_main_status_health_prints_health_report(tmp_repo, tmp_home, monkeypatch, capsys):
    # `status health` is a health report (os/deps/profile/mboard/drift SUMMARY),
    # distinct from status's per-file listing.
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    with open(os.path.join(tmp_repo, "home", ".claude", "settings.json"), "w") as fh:
        fh.write('{"model": "opus"}\n')

    rc = cli.main(["status", "health"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "ccpkg status health" in out
    assert "os\t" in out
    assert "dep git\t" in out
    assert "profile\t" in out
    assert "mboard\t" in out
    assert "drift\t" in out                    # summary line, not per-file


def test_status_and_status_health_differ(tmp_repo, tmp_home, monkeypatch, capsys):
    # Regression: `status` and `status health` must NOT print identical output
    # (they used to be the same function).
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    cli.main(["status"])
    status_out = capsys.readouterr().out
    cli.main(["status", "health"])
    health_out = capsys.readouterr().out
    assert status_out != health_out
    # a health-only marker that status never prints
    assert "dep git\t" in health_out and "dep git\t" not in status_out


def test_main_uninstall_yes_removes_profile_and_mboard(tmp_repo, tmp_home,
                                                        monkeypatch, capsys):
    from ccpkg import profile
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    # Fake an installed tree in the live home.
    profile.save(tmp_home, profile.Profile(selected=["statusline.sh"], deselected=[]))
    os.makedirs(os.path.join(tmp_home, "mboard"))
    with open(os.path.join(tmp_home, "statusline.sh"), "w") as fh:
        fh.write("live")

    rc = cli.main(["uninstall", "--yes"])     # --yes skips the confirm prompt

    assert rc == 0
    out = capsys.readouterr().out
    assert "mboard\tremoved" in out
    assert profile.load(tmp_home) is None
    assert not os.path.isdir(os.path.join(tmp_home, "mboard"))


def test_main_uninstall_refuses_without_yes_when_not_tty(tmp_repo, tmp_home,
                                                         monkeypatch, capsys):
    # Regression: piped/non-interactive uninstall WITHOUT --yes must refuse and
    # remove NOTHING (it previously skipped the prompt and ran destructively).
    from ccpkg import profile
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: False)   # non-interactive
    profile.save(tmp_home, profile.Profile(selected=["statusline.sh"], deselected=[]))
    os.makedirs(os.path.join(tmp_home, "mboard"))

    rc = cli.main(["uninstall"])               # no --yes, no TTY

    assert rc == 2                              # refused
    assert profile.load(tmp_home) is not None   # nothing removed
    assert os.path.isdir(os.path.join(tmp_home, "mboard"))
    assert "refusing" in capsys.readouterr().err.lower()


def test_uninstall_parser_accepts_yes():
    parser = cli._build_parser()
    args = parser.parse_args(["uninstall", "--yes"])
    assert args.yes is True


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


def _stub_install(*a, **k):
    # A fast installer.install double: a valid empty InstallReport, no side effects.
    return installer.InstallReport(
        os="darwin", deps={}, base_applied=[], overlay_applied=[],
        plugins={}, mboard={}, scan_findings=[], notes=[],
    )


def test_apply_headless_writes_no_profile(tmp_repo, tmp_home, monkeypatch):
    from ccpkg import cli, profile
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: False)   # non-TTY => headless
    # `apply` with no preset on a non-TTY stdin and NO prior profile applies
    # defaults headlessly; the wizard never ran, so NO profile is persisted
    # (the wizard owns the profile).
    rc = cli.main(["apply"])
    assert rc == 0
    assert profile.load(tmp_home) is None


def test_apply_wizard_path_writes_profile(tmp_repo, tmp_home, monkeypatch):
    from ccpkg import cli, profile, wizard
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(wizard, "run_wizard",
                        lambda stages, pre, existing=False: {"settings.json"})
    monkeypatch.setattr(installer, "install", _stub_install)

    rc = cli.main(["apply"])           # interactive TTY path, no prior profile
    assert rc == 0
    prof = profile.load(tmp_home)
    assert prof is not None
    assert prof.selected == ["settings.json"]


def test_apply_rerun_with_profile_writes_profile(tmp_repo, tmp_home, monkeypatch):
    # The old `--reconfigure` flag is gone: re-running `apply` (interactive, with a
    # saved profile) already reopens the picker and persists the new selection.
    from ccpkg import cli, profile, wizard
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    profile.save(tmp_home, profile.Profile(selected=["settings.json"], deselected=[]))
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(wizard, "run_wizard",
                        lambda stages, pre, existing=False:
                        {"settings.json", "statusline.sh"})
    monkeypatch.setattr(installer, "install", _stub_install)

    rc = cli.main(["apply"])
    assert rc == 0
    prof = profile.load(tmp_home)
    assert set(prof.selected) == {"settings.json", "statusline.sh"}


def test_apply_headless_replay_does_not_rewrite_profile(tmp_repo, tmp_home, monkeypatch):
    # Headless replay (non-TTY `apply` with a saved profile) applies the profile
    # and must NOT rewrite it — the wizard never ran.
    from ccpkg import cli, profile
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: False)   # non-TTY => headless
    profile.save(tmp_home, profile.Profile(selected=["settings.json"],
                                           deselected=["statusline.sh"]))
    monkeypatch.setattr(installer, "install", _stub_install)

    saved = {"called": False}
    monkeypatch.setattr(profile, "save",
                        lambda *a, **k: saved.__setitem__("called", True))

    rc = cli.main(["apply"])             # headless replay
    assert rc == 0
    assert saved["called"] is False      # headless replay must NOT rewrite


def test_apply_rerun_reopens_picker_and_rewrites(tmp_repo, tmp_home, monkeypatch):
    # The update flow: an interactive re-run WITH a saved profile reopens the
    # picker (pre-filled) and persists the (possibly changed) selection.
    from ccpkg import cli, profile, wizard
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    profile.save(tmp_home, profile.Profile(selected=["settings.json"], deselected=[]))
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(installer, "install", _stub_install)

    seen = {}

    def fake_wizard(stages, pre, existing=False):
        seen["existing"] = existing
        return {"settings.json", "statusline.sh"}  # user toggled one on

    monkeypatch.setattr(wizard, "run_wizard", fake_wizard)

    rc = cli.main(["apply"])             # re-running apply still reopens the picker
    assert rc == 0
    assert seen["existing"] is True      # splash knows it's a re-run
    prof = profile.load(tmp_home)
    assert set(prof.selected) == {"settings.json", "statusline.sh"}


def test_apply_ctrl_c_during_wizard_cancels(tmp_repo, tmp_home, monkeypatch, capsys):
    from ccpkg import cli, wizard
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)

    def _boom(stages, pre, existing=False):
        raise KeyboardInterrupt

    monkeypatch.setattr(wizard, "run_wizard", _boom)

    def _no_install(*a, **k):
        raise AssertionError("installer.install must not run after Ctrl-C")

    monkeypatch.setattr(installer, "install", _no_install)

    rc = cli.main(["apply"])
    assert rc == 130
    assert "cancelled" in capsys.readouterr().out.lower()


def test_apply_parser_accepts_source_positional():
    from ccpkg import cli
    parser = cli._build_parser()
    # the positional is now a generic `source` (preset | url | path)
    for name in ("minimal", "recommended", "everything"):
        args = parser.parse_args(["apply", name])
        assert args.source == name
    args = parser.parse_args(["apply", "https://github.com/a/b"])
    assert args.source == "https://github.com/a/b"
    # default: no source
    args = parser.parse_args(["apply"])
    assert args.source is None


def test_apply_everything_selects_all(tmp_repo, tmp_home, monkeypatch):
    # `apply everything` is headless: skips the wizard, applies ALL surfaced ids,
    # and writes NO profile.
    from ccpkg import cli, profile, wizard, selectables, selection, manifest
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)   # would be interactive

    def _no_wizard(*a, **k):
        raise AssertionError("wizard must not run with a preset")

    monkeypatch.setattr(wizard, "run_wizard", _no_wizard)

    captured = {}

    def _capture_install(root, home_target, env, os_name, run=subprocess.run,
                         interactive=False, selected=None):
        captured["selected"] = selected
        return installer.InstallReport(
            os=os_name, deps={}, base_applied=[], overlay_applied=[],
            plugins={}, mboard={}, scan_findings=[], notes=[],
        )

    monkeypatch.setattr(installer, "install", _capture_install)

    rc = cli.main(["apply", "everything"])
    assert rc == 0
    items = manifest.parse(cli.config.manifest_path(tmp_repo))
    expected = cli._all_ids(items, selectables.SELECTABLES, False)
    assert captured["selected"] == expected
    assert profile.load(tmp_home) is None   # headless: no profile written


def test_apply_recommended_matches_defaults(tmp_repo, tmp_home, monkeypatch):
    from ccpkg import cli, selectables, selection, manifest
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    captured = {}

    def _capture_install(root, home_target, env, os_name, run=subprocess.run,
                         interactive=False, selected=None):
        captured["selected"] = selected
        return installer.InstallReport(
            os=os_name, deps={}, base_applied=[], overlay_applied=[],
            plugins={}, mboard={}, scan_findings=[], notes=[],
        )

    monkeypatch.setattr(installer, "install", _capture_install)

    rc = cli.main(["apply", "recommended"])
    assert rc == 0
    items = manifest.parse(cli.config.manifest_path(tmp_repo))
    expected = selection.default_ids(items, selectables.SELECTABLES, False)
    assert captured["selected"] == expected


def test_apply_minimal_is_required_only(tmp_repo, tmp_home, monkeypatch):
    # minimal = required-only. The fixture manifest marks nothing required, so the
    # minimal set is empty — and crucially is NOT the default-on set.
    from ccpkg import cli, selectables, selection, manifest
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    captured = {}

    def _capture_install(root, home_target, env, os_name, run=subprocess.run,
                         interactive=False, selected=None):
        captured["selected"] = selected
        return installer.InstallReport(
            os=os_name, deps={}, base_applied=[], overlay_applied=[],
            plugins={}, mboard={}, scan_findings=[], notes=[],
        )

    monkeypatch.setattr(installer, "install", _capture_install)

    rc = cli.main(["apply", "minimal"])
    assert rc == 0
    items = manifest.parse(cli.config.manifest_path(tmp_repo))
    defaults = selection.default_ids(items, selectables.SELECTABLES, False)
    assert captured["selected"] == set()
    assert captured["selected"] != defaults


def test_apply_renders_summary_on_interactive_tty(tmp_repo, tmp_home, monkeypatch):
    # On the interactive TTY path, after the plain report we ALSO call
    # wizard.render_summary(summary, out) with the agreed dict shape.
    from ccpkg import cli, wizard, profile
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
    monkeypatch.setattr(wizard, "run_wizard",
                        lambda stages, pre, existing=False: {"settings.json"})

    def _report_install(root, home_target, env, os_name, run=subprocess.run,
                        interactive=False, selected=None):
        return installer.InstallReport(
            os=os_name, deps={"git": "present"},
            base_applied=[("settings.json", "merged")],
            overlay_applied=[("commands/private.md", "linked")],
            plugins={"superpowers": "installed"},
            mboard={"daemon": "running"},
            scan_findings=[], notes=["a note"],
        )

    monkeypatch.setattr(installer, "install", _report_install)

    captured = {}
    monkeypatch.setattr(wizard, "render_summary",
                        lambda summary, out: captured.update(summary=summary, out=out),
                        raising=False)

    rc = cli.main(["apply"])
    assert rc == 0
    s = captured["summary"]
    assert s["applied"] == [("settings.json", "merged"),
                            ("commands/private.md", "linked")]
    assert s["plugins"] == {"superpowers": "installed"}
    assert s["mboard"] == {"daemon": "running"}
    assert s["notes"] == ["a note"]
    assert isinstance(s["skipped"], list)        # ids not selected
    assert "settings.json" not in s["skipped"]   # it WAS selected


def test_apply_summary_skipped_when_not_tty(tmp_repo, tmp_home, monkeypatch):
    # Headless / non-TTY path must NOT call render_summary (keeps plain output
    # parseable and avoids styled noise in pipes).
    from ccpkg import cli, wizard
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: False)   # non-TTY => headless
    monkeypatch.setattr(installer, "install", _stub_install)

    called = {"render": False}
    monkeypatch.setattr(wizard, "render_summary",
                        lambda summary, out: called.__setitem__("render", True),
                        raising=False)

    rc = cli.main(["apply"])              # headless
    assert rc == 0
    assert called["render"] is False


def test_apply_summary_guarded_when_render_absent(tmp_repo, tmp_home, monkeypatch):
    # If wizard.render_summary hasn't landed yet, the interactive apply must
    # still succeed (getattr guard) rather than crash.
    from ccpkg import cli, wizard
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
    monkeypatch.setattr(wizard, "run_wizard",
                        lambda stages, pre, existing=False: {"settings.json"})
    monkeypatch.setattr(installer, "install", _stub_install)
    # Ensure the attribute is absent.
    monkeypatch.delattr(wizard, "render_summary", raising=False)

    rc = cli.main(["apply"])
    assert rc == 0


def test_apply_applies_synthetic_extra_manifest_item(tmp_repo, tmp_home, monkeypatch):
    # New installables flow generically: a manifest item added by 'content' (here
    # a synthetic default-on symlink) is applied by a headless apply with no
    # cli/flow changes needed.
    from ccpkg import cli
    _seed_localenv(tmp_repo, tmp_home)
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: False)   # non-TTY => headless

    # Add a brand-new manifest item + its source file.
    manifest_path = os.path.join(tmp_repo, "manifest.json")
    with open(manifest_path) as fh:
        data = json.load(fh)
    data["items"].append({
        "path": "commands/brand-new.md", "mode": "symlink",
        "os": "any", "layer": "base", "group": "Commands",
        "desc": "a freshly surfaced command", "default": True,
    })
    with open(manifest_path, "w") as fh:
        json.dump(data, fh, indent=2)
    src_cmd = os.path.join(tmp_repo, "home", ".claude", "commands")
    os.makedirs(src_cmd, exist_ok=True)
    with open(os.path.join(src_cmd, "brand-new.md"), "w") as fh:
        fh.write("# brand new command\n")

    rc = cli.main(["apply"])              # headless: defaults => includes new item
    assert rc == 0
    applied = os.path.join(tmp_home, "commands", "brand-new.md")
    assert os.path.exists(applied)


def test_version_flag_prints_version(capsys):
    from ccpkg import cli, __version__
    import pytest
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out
    assert out.startswith("ccpkg ")


def test_dunder_main_calls_sys_exit(tmp_repo, tmp_home, monkeypatch):
    # python3 -m ccpkg with no args -> nonzero exit via sys.exit(main()).
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(cli.__file__)))
    proc = subprocess.run(
        [sys.executable, "-m", "ccpkg"],
        env=env, capture_output=True, text=True,
    )
    assert proc.returncode != 0
