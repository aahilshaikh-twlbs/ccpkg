import json
import os

import pytest

from ccpkg import config, installer, plugins, scan


def _run_install(e2e_repo, fake_run):
    """Helper: run a full install over the e2e scenario via fake_run."""
    return installer.install(
        root=e2e_repo["root"],
        home_target=e2e_repo["home"],
        env=e2e_repo["env"],
        os_name="darwin",
        run=fake_run,
    )


def _live_settings(home):
    with open(os.path.join(home, "settings.json")) as f:
        return json.load(f)


def test_install_returns_report_for_detected_os(e2e_repo, fake_run):
    report = _run_install(e2e_repo, fake_run)
    assert isinstance(report, installer.InstallReport)
    assert report.os == "darwin"


def test_base_items_applied(e2e_repo, fake_run):
    report = _run_install(e2e_repo, fake_run)
    applied_paths = [p for (p, _result) in report.base_applied]
    assert "settings.json" in applied_paths
    assert "commands/handoff.md" in applied_paths


def test_overlay_items_applied(e2e_repo, fake_run):
    report = _run_install(e2e_repo, fake_run)
    applied_paths = [p for (p, _result) in report.overlay_applied]
    assert "commands/private.md" in applied_paths
    assert os.path.lexists(os.path.join(e2e_repo["home"], "commands", "private.md"))


def test_settings_merge_keeps_base_keys(e2e_repo, fake_run):
    _run_install(e2e_repo, fake_run)
    live = _live_settings(e2e_repo["home"])
    # base-managed scalar wins over the pre-existing live value
    assert live["model"] == "opus"


def test_settings_merge_preserves_preexisting_live_key(e2e_repo, fake_run):
    _run_install(e2e_repo, fake_run)
    live = _live_settings(e2e_repo["home"])
    # the live-only key the base never managed survives the merge
    assert live["theme"] == "dark"


def test_plugin_settings_present_after_install(e2e_repo, fake_run):
    _run_install(e2e_repo, fake_run)
    live = _live_settings(e2e_repo["home"])
    enabled = live.get("enabledPlugins", {})
    for plugin_id in plugins.PLUGINS:
        assert enabled.get(plugin_id) is True
    for name in plugins.MARKETPLACES:
        assert name in live.get("extraKnownMarketplaces", {})


def test_mboard_install_invoked(e2e_repo, fake_run):
    report = _run_install(e2e_repo, fake_run)
    # mboard_install.install returns a status dict; installer records it on the report
    assert isinstance(report.mboard, dict)
    assert report.mboard != {}


def test_scan_over_base_is_clean(e2e_repo, fake_run):
    report = _run_install(e2e_repo, fake_run)
    assert scan.is_clean(report.scan_findings)


def _seed_purity_terms(root, *terms):
    ccpkg_dir = os.path.join(root, ".ccpkg")
    os.makedirs(ccpkg_dir, exist_ok=True)
    with open(os.path.join(ccpkg_dir, "purity-terms.txt"), "w") as fh:
        fh.write("\n".join(terms) + "\n")


def test_scan_blocks_purity_hit_in_base(e2e_repo):
    _seed_purity_terms(e2e_repo["root"], "acmecorp")
    base_src = config.home_claude_src(e2e_repo["root"])
    planted = os.path.join(base_src, "commands", "handoff.md")
    with open(planted, "w") as f:
        f.write("# handoff\nThis references acmecorp internal flow.\n")
    terms = scan.load_purity_terms(e2e_repo["root"])
    findings = scan.scan_paths([planted], "base", terms)
    assert not scan.is_clean(findings)
    assert any(fnd.rule == "purity" for fnd in findings)


def test_scan_allows_purity_hit_in_overlay_layer(e2e_repo):
    # purity applies ONLY to layer == "base" (Contract §8)
    _seed_purity_terms(e2e_repo["root"], "acmecorp")
    base_src = config.home_claude_src(e2e_repo["root"])
    planted = os.path.join(base_src, "commands", "handoff.md")
    with open(planted, "w") as f:
        f.write("# handoff\nThis references acmecorp internal flow.\n")
    terms = scan.load_purity_terms(e2e_repo["root"])
    findings = scan.scan_paths([planted], "overlay", terms)
    assert scan.is_clean(findings)


def test_scan_blocks_secret_in_base_layer(e2e_repo):
    base_src = config.home_claude_src(e2e_repo["root"])
    planted = os.path.join(base_src, "commands", "handoff.md")
    with open(planted, "w") as f:
        f.write("token = sk-ABCDEFGHIJKLMNOPQRSTUVWX\n")
    terms = scan.load_purity_terms(e2e_repo["root"])
    findings = scan.scan_paths([planted], "base", terms)
    assert not scan.is_clean(findings)
    assert any(fnd.rule == "secret" for fnd in findings)


def test_scan_blocks_secret_in_overlay_layer(e2e_repo):
    # secrets block in EITHER layer (Contract §8: always secrets)
    overlay_file = os.path.join(
        e2e_repo["overlay_dir"], "home", ".claude", "commands", "private.md"
    )
    with open(overlay_file, "w") as f:
        f.write("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345\n")
    terms = scan.load_purity_terms(e2e_repo["root"])
    findings = scan.scan_paths([overlay_file], "overlay", terms)
    assert not scan.is_clean(findings)
    assert any(fnd.rule == "secret" for fnd in findings)


def test_install_never_raises_when_a_step_fails(e2e_repo, monkeypatch):
    # Contract §12: install never raises on sub-step failure; collect into notes.
    def boom_run(*args, **kwargs):
        raise OSError("simulated subprocess failure")
    report = installer.install(
        root=e2e_repo["root"],
        home_target=e2e_repo["home"],
        env=e2e_repo["env"],
        os_name="linux",
        run=boom_run,
    )
    assert isinstance(report, installer.InstallReport)
    assert report.os == "linux"
    # file work still happened despite subprocess steps failing
    applied_paths = [p for (p, _result) in report.base_applied]
    assert "settings.json" in applied_paths
