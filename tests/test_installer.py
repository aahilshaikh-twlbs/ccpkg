import os
import subprocess

import pytest

from ccpkg import installer
from ccpkg.installer import InstallReport, install, clone_overlay


def _env(overlay_dir="", overlay_repo="", vault_root=""):
    # Minimal env dict in the shape localenv.load() produces (contract §3 DEFAULTS keys).
    return {
        "CODE_ROOT": os.path.expanduser("~/Documents/Code"),
        "VAULT_ROOT": vault_root,
        "AWS_PROFILE": "",
        "OVERLAY_REPO": overlay_repo,
        "OVERLAY_DIR": overlay_dir,
    }


def _patch_substeps(monkeypatch, calls):
    # Replace every heavy collaborator with a recording fake so install() does no real I/O
    # beyond apply_layer (which writes into the tmp_home/tmp_repo sandbox).
    monkeypatch.setattr(
        installer.osenv, "ensure_deps",
        lambda os_name, pkgs, run=None: (calls.setdefault("deps", (os_name, list(pkgs))), {"git": "present", "python3": "present", "jq": "installed"})[1],
    )
    monkeypatch.setattr(
        installer.plugins, "cli_install",
        lambda run=None, have=None: (calls.__setitem__("plugins", True), {"superpowers@claude-plugins-official": "installed"})[1],
    )
    monkeypatch.setattr(
        installer.mailbox_install, "install",
        lambda root, home_target, run=None: (calls.__setitem__("mailbox", (root, home_target)), {"mailbox": "linked"})[1],
    )
    monkeypatch.setattr(
        installer.scan, "load_purity_terms",
        lambda root: ["acmecorp"],
    )
    monkeypatch.setattr(
        installer.scan, "scan_paths",
        lambda paths, layer, terms: (calls.__setitem__("scan", (list(paths), layer)), [])[1],
    )


def test_install_dry_run_base_only(tmp_home, tmp_repo, fake_run, monkeypatch):
    calls = {}
    _patch_substeps(monkeypatch, calls)

    report = install(tmp_repo, tmp_home, _env(), "darwin", run=fake_run)

    assert isinstance(report, InstallReport)
    assert report.os == "darwin"
    # Step 1: deps requested with the exact pkg list from the contract.
    assert calls["deps"] == ("darwin", ["git", "python3", "jq"])
    assert report.deps == {"git": "present", "python3": "present", "jq": "installed"}
    # Step 3: base layer applied (tmp_repo's manifest base item -> a (path,result) tuple).
    assert report.base_applied, "base layer should have been applied"
    assert all(isinstance(t, tuple) and len(t) == 2 for t in report.base_applied)
    # Step 4: no OVERLAY_DIR/REPO -> overlay empty.
    assert report.overlay_applied == []
    # Steps 5 & 6 invoked.
    assert calls["plugins"] is True
    assert calls["mailbox"] == (tmp_repo, tmp_home)
    assert report.plugins == {"superpowers@claude-plugins-official": "installed"}
    assert report.mailbox == {"mailbox": "linked"}
    # Step 7: scan ran over the BASE source layer.
    assert calls["scan"][1] == "base"
    assert report.scan_findings == []


def test_install_applies_overlay_when_overlay_dir_set(tmp_home, tmp_repo, fake_run, monkeypatch):
    calls = {}
    _patch_substeps(monkeypatch, calls)

    # Build a fake overlay tree with its own manifest + a home/.claude file.
    overlay_dir = os.path.join(str(tmp_repo), "_overlay")
    os.makedirs(os.path.join(overlay_dir, "home", ".claude"), exist_ok=True)
    with open(os.path.join(overlay_dir, "manifest.json"), "w") as f:
        f.write('{"items": [{"path": "ov.txt", "mode": "template", "os": "any", "layer": "overlay"}]}')
    with open(os.path.join(overlay_dir, "home", ".claude", "ov.txt"), "w") as f:
        f.write("overlay-content\n")

    report = install(tmp_repo, tmp_home, _env(overlay_dir=overlay_dir), "linux", run=fake_run)

    assert report.os == "linux"
    assert report.overlay_applied, "overlay layer should have been applied when OVERLAY_DIR is set"
    assert all(isinstance(t, tuple) and len(t) == 2 for t in report.overlay_applied)


def test_install_never_raises_when_a_step_fails(tmp_home, tmp_repo, fake_run, monkeypatch):
    calls = {}
    _patch_substeps(monkeypatch, calls)

    # Make plugins blow up; install() must swallow it and record a note, still returning a report.
    def boom(run=None, have=None):
        raise RuntimeError("claude CLI exploded")
    monkeypatch.setattr(installer.plugins, "cli_install", boom)

    report = install(tmp_repo, tmp_home, _env(), "darwin", run=fake_run)

    assert isinstance(report, InstallReport)
    # The failure surfaced in notes, not as an exception.
    assert any("plugins" in n and "claude CLI exploded" in n for n in report.notes)
    # Other steps still ran (mailbox after plugins).
    assert calls["mailbox"] == (tmp_repo, tmp_home)


def test_install_records_scan_findings(tmp_home, tmp_repo, fake_run, monkeypatch):
    calls = {}
    _patch_substeps(monkeypatch, calls)
    finding = installer.scan.Finding(path="settings.json", line=3, rule="purity", detail="acmecorp")
    monkeypatch.setattr(installer.scan, "scan_paths", lambda paths, layer, terms: [finding])

    report = install(tmp_repo, tmp_home, _env(), "darwin", run=fake_run)

    assert report.scan_findings == [finding]
    # Findings are reported, not fatal — install still completed every step.
    assert report.base_applied
    assert report.mailbox == {"mailbox": "linked"}


def test_install_auth_note_when_claude_present_and_logged_out(tmp_home, tmp_repo, fake_run, monkeypatch):
    calls = {}
    _patch_substeps(monkeypatch, calls)
    monkeypatch.setattr(installer.osenv, "have", lambda cmd: cmd == "claude")

    def auth_run(cmd, **kwargs):
        # `claude auth status` returns non-zero when logged out.
        if list(cmd[:2]) == ["claude", "auth"]:
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="not logged in")
        return fake_run(cmd, **kwargs)

    report = install(tmp_repo, tmp_home, _env(), "darwin", run=auth_run)

    assert any("claude auth login" in n for n in report.notes)


def test_clone_overlay_returns_existing_dir(tmp_path):
    d = tmp_path / "ov"
    d.mkdir()
    env = _env(overlay_dir=str(d))
    assert clone_overlay(env) == str(d)


def test_clone_overlay_clones_repo_into_cache(tmp_home, fake_run, monkeypatch):
    # No OVERLAY_DIR, but OVERLAY_REPO set -> git clone into ~/.cache/ccpkg/overlay.
    env = _env(overlay_repo="git@example.com:me/overlay.git")
    cache = os.path.join(str(tmp_home), "_cache_overlay")
    monkeypatch.setattr(installer, "_overlay_cache_dir", lambda: cache)

    result = clone_overlay(env, run=fake_run)

    assert result == cache
    # A git clone of the repo into the cache dir was issued. The conftest fake_run
    # records each invocation as the raw argv (list), not a dict.
    assert any(
        list(c[:2]) == ["git", "clone"] and env["OVERLAY_REPO"] in c
        for c in fake_run.calls
    )


def test_clone_overlay_none_when_unset(tmp_path):
    assert clone_overlay(_env()) is None


def test_clone_overlay_never_raises_on_git_failure(tmp_home, monkeypatch):
    env = _env(overlay_repo="git@example.com:me/overlay.git")
    monkeypatch.setattr(installer, "_overlay_cache_dir", lambda: os.path.join(str(tmp_home), "ovc"))

    def failing_run(cmd, **kwargs):
        raise OSError("git not found")

    # Must not raise; returns None on clone failure.
    assert clone_overlay(env, run=failing_run) is None
