import json
import os
from pathlib import Path

import pytest

from ccpkg import share, scan, profile, cli, installer

ROOT = Path(__file__).resolve().parents[1]


# ---- source classification ---------------------------------------------

def test_is_preset_and_repo_detection():
    assert share.is_preset("recommended")
    assert not share.is_preset("./x.json")
    assert share._looks_like_repo("https://github.com/a/b")
    assert share._looks_like_repo("git@github.com:a/b.git")
    assert share._looks_like_repo("ssh://git@h/x.git")
    assert not share._looks_like_repo("./local.json")
    assert not share._looks_like_repo("/abs/path/ccpkg.share.json")


# ---- export (uses the real repo catalog for rich labels) ----------------

def test_export_setup_from_profile(tmp_path):
    home = str(tmp_path)
    profile.save(home, profile.Profile(
        selected=["agents/debugger.md", "superpowers"],
        deselected=["agents/a11y.md"]))
    data = share.export_setup(str(ROOT), home)
    assert data["ccpkg_share"] == share.SHARE_SCHEMA
    assert data["selected"] == ["agents/debugger.md", "superpowers"]
    ids = {it["id"] for it in data["items"]}
    assert ids == {"agents/debugger.md", "superpowers"}
    dbg = next(it for it in data["items"] if it["id"] == "agents/debugger.md")
    assert dbg["group"] == "Agents" and dbg["desc"]


def test_export_setup_no_profile_uses_defaults(tmp_path):
    data = share.export_setup(str(ROOT), str(tmp_path))
    assert data["ccpkg_share"] == share.SHARE_SCHEMA
    assert len(data["selected"]) > 0


def test_export_artifact_is_scan_clean(tmp_path):
    profile.save(str(tmp_path),
                 profile.Profile(selected=["agents/debugger.md"], deselected=[]))
    data = share.export_setup(str(ROOT), str(tmp_path))
    findings = scan.scan_text_purity(
        json.dumps(data), scan.load_purity_terms(str(ROOT)), share.SHARE_FILENAME)
    assert not findings


# ---- write / fetch round-trip -------------------------------------------

def test_write_and_fetch_roundtrip(tmp_path):
    data = {"ccpkg_share": 1, "selected": ["a", "b"], "deselected": [], "items": []}
    p = os.path.join(str(tmp_path), share.SHARE_FILENAME)
    share.write_share(data, p)
    assert share.fetch_share(p)["selected"] == ["a", "b"]
    # resolvable from the containing directory too
    assert share.fetch_share(str(tmp_path))["selected"] == ["a", "b"]


def test_fetch_share_invalid(tmp_path):
    with pytest.raises(ValueError):
        share.fetch_share(os.path.join(str(tmp_path), "nope.json"))
    bad = os.path.join(str(tmp_path), share.SHARE_FILENAME)
    with open(bad, "w") as fh:
        fh.write('{"not": "a share"}')
    with pytest.raises(ValueError):
        share.fetch_share(bad)


def test_fetch_share_from_repo_uses_clone():
    # injected run "clones" by writing the share file into the clone target dir.
    seen = {}

    def fake_run(argv, **kw):
        dest = argv[-1]
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, share.SHARE_FILENAME), "w") as fh:
            json.dump({"ccpkg_share": 1, "selected": ["x"], "deselected": [],
                       "items": []}, fh)
        seen["argv"] = argv

        class _R:
            returncode = 0
        return _R()

    data = share.fetch_share("https://github.com/a/b", run=fake_run)
    assert data["selected"] == ["x"]
    assert seen["argv"][:2] == ["git", "clone"]


# ---- resolve against this machine's catalog -----------------------------

def test_resolve_selection_skips_unknown():
    data = {"ccpkg_share": 1,
            "selected": ["agents/debugger.md", "totally-not-real-xyz"],
            "deselected": [], "items": []}
    resolved, preview, skipped = share.resolve_selection(data, str(ROOT))
    assert "agents/debugger.md" in resolved
    assert "totally-not-real-xyz" not in resolved
    assert skipped == ["totally-not-real-xyz"]
    assert any(p["id"] == "agents/debugger.md" for p in preview)


# ---- CLI integration -----------------------------------------------------

def _seed_localenv(repo):
    with open(os.path.join(repo, "local.env"), "w") as fh:
        fh.write("OVERLAY_REPO=\nOVERLAY_DIR=\nVAULT_ROOT=\n")


def test_cmd_share_writes_artifact(tmp_repo, tmp_home, monkeypatch):
    _seed_localenv(tmp_repo)
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    profile.save(tmp_home, profile.Profile(selected=["settings.json"], deselected=[]))
    out = os.path.join(tmp_home, "my.share.json")

    rc = cli.main(["share", out])

    assert rc == 0
    data = json.load(open(out))
    assert data["ccpkg_share"] == share.SHARE_SCHEMA
    assert data["selected"] == ["settings.json"]


def test_apply_source_adopts_shared_setup(tmp_repo, tmp_home, monkeypatch, capsys):
    _seed_localenv(tmp_repo)
    monkeypatch.setattr(cli.config, "repo_root", lambda: tmp_repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: tmp_home)
    # a share file whose selection exists in tmp_repo's catalog
    sharefile = os.path.join(tmp_home, share.SHARE_FILENAME)
    with open(sharefile, "w") as fh:
        json.dump({"ccpkg_share": 1, "selected": ["settings.json"],
                   "deselected": [], "items": []}, fh)
    captured = {}

    def _fake_install(root, home_target, env, os_name, run=None, selected=None):
        captured["selected"] = selected
        return installer.InstallReport(os=os_name)

    monkeypatch.setattr(cli.installer, "install", _fake_install)

    rc = cli.main(["apply", sharefile])   # non-TTY under pytest -> no confirm

    assert rc == 0
    assert captured["selected"] == {"settings.json"}
    # adopting persists the selection as this machine's profile
    saved = profile.load(tmp_home)
    assert saved is not None and "settings.json" in saved.selected
