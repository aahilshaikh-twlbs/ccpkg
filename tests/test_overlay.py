import json
import os

from ccpkg import overlay


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def test_init_scaffolds_tree_and_wires_localenv(tmp_path):
    dest = str(tmp_path / "ov")
    le = str(tmp_path / "local.env")

    result = overlay.init(dest=dest, localenv_path=le)

    # Directory tree mirrors the base layout.
    assert os.path.isdir(dest)
    assert os.path.isdir(os.path.join(dest, "home", ".claude"))
    assert os.path.isdir(os.path.join(dest, "home", ".claude", "agents"))

    # Starter manifest json-parses to {"items": []}.
    manifest_file = os.path.join(dest, "manifest.json")
    assert os.path.isfile(manifest_file)
    assert json.loads(_read(manifest_file)) == {"items": []}

    # README explaining the overlay exists.
    assert os.path.isfile(os.path.join(dest, "README.md"))

    # local.env now wires OVERLAY_DIR=<dest>.
    assert os.path.isfile(le)
    assert "OVERLAY_DIR={0}".format(dest) in _read(le)

    # Returned actions dict shape.
    assert result["dest"] == dest
    assert result["localenv"] == "OVERLAY_DIR={0}".format(dest)
    assert result["git"] is False
    assert "exists" not in result


def test_init_with_repo_wires_overlay_repo(tmp_path):
    dest = str(tmp_path / "ov")
    le = str(tmp_path / "local.env")

    result = overlay.init(
        dest=dest, localenv_path=le, repo="https://example.com/x.git"
    )

    text = _read(le)
    assert "OVERLAY_REPO=https://example.com/x.git" in text
    # OVERLAY_DIR is left alone when a repo is given.
    assert "OVERLAY_DIR=" not in text
    assert result["localenv"] == "OVERLAY_REPO=https://example.com/x.git"


def test_init_preserves_unrelated_localenv_keys(tmp_path):
    dest = str(tmp_path / "ov")
    le = str(tmp_path / "local.env")
    with open(le, "w", encoding="utf-8") as fh:
        fh.write("FOO=bar\n")

    overlay.init(dest=dest, localenv_path=le)

    text = _read(le)
    # The unrelated key survives and the overlay key is appended.
    assert "FOO=bar" in text
    assert "OVERLAY_DIR={0}".format(dest) in text


def test_init_twice_does_not_clobber_manifest(tmp_path):
    dest = str(tmp_path / "ov")
    le = str(tmp_path / "local.env")

    overlay.init(dest=dest, localenv_path=le)

    # Write a sentinel item into the manifest.
    manifest_file = os.path.join(dest, "manifest.json")
    sentinel = {"items": [{"path": "agents/keep.md", "mode": "symlink",
                           "os": "any", "layer": "overlay"}]}
    with open(manifest_file, "w", encoding="utf-8") as fh:
        json.dump(sentinel, fh, indent=2)

    result = overlay.init(dest=dest, localenv_path=le)

    # Sentinel survives; result reports the manifest already existed.
    assert json.loads(_read(manifest_file)) == sentinel
    assert result["exists"]
    # local.env wiring is still ensured (and not duplicated).
    text = _read(le)
    assert text.count("OVERLAY_DIR={0}".format(dest)) == 1


def test_init_with_git_records_git_init_call(tmp_path, fake_run, monkeypatch):
    dest = str(tmp_path / "ov")
    le = str(tmp_path / "local.env")
    # Make git "available" so do_git proceeds regardless of the host.
    monkeypatch.setattr(overlay.osenv, "have", lambda cmd: True)

    result = overlay.init(
        dest=dest, localenv_path=le, do_git=True, run=fake_run
    )

    assert result["git"] is True
    # The stub recorded a git-init-style argv.
    assert len(fake_run.calls) == 1
    argv = list(fake_run.calls[0])
    assert argv[0] == "git"
    assert argv[1] == "init"
    assert dest in argv


def test_init_skips_git_when_unavailable(tmp_path, fake_run, monkeypatch):
    dest = str(tmp_path / "ov")
    le = str(tmp_path / "local.env")
    monkeypatch.setattr(overlay.osenv, "have", lambda cmd: False)

    result = overlay.init(
        dest=dest, localenv_path=le, do_git=True, run=fake_run
    )

    assert result["git"] is False
    assert fake_run.calls == []
