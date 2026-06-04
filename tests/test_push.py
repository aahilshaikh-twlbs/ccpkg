import json
import os

from ccpkg import config, localenv
from ccpkg.manifest import Item
from ccpkg import push


def _env_with_overlay(overlay_dir):
    # Mirror localenv.template_vars shape: HOME plus the machine vars.
    return {
        "HOME": os.path.expanduser("~"),
        "CODE_ROOT": "/Users/example/Documents/Code",
        "VAULT_ROOT": "",
        "AWS_PROFILE": "",
        "OVERLAY_DIR": overlay_dir,
    }


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_classify_returns_layer_or_none():
    items = [
        Item(path="settings.json", mode="merge", os="any", layer="base"),
        Item(path="agents/me.md", mode="template", os="any", layer="overlay"),
    ]
    assert push.classify("settings.json", items) == "base"
    assert push.classify("agents/me.md", items) == "overlay"
    assert push.classify("notes/scratch.md", items) is None


def test_changed_base_file_captured_and_reverse_templatized(tmp_path):
    root = str(tmp_path / "repo")
    home = str(tmp_path / "home")
    overlay = str(tmp_path / "overlay")
    os.makedirs(overlay, exist_ok=True)
    # manifest declares hello.md as a base item.
    _write(
        config.manifest_path(root),
        json.dumps({"items": [{"path": "hello.md", "mode": "template",
                               "os": "any", "layer": "base"}]}),
    )
    # repo currently has a templated version; home has a machine-expanded edit.
    base_src = config.home_claude_src(root)
    _write(os.path.join(base_src, "hello.md"), "root is ${CODE_ROOT}\n")
    _write(os.path.join(home, "hello.md"),
           "root is /Users/example/Documents/Code now\n")
    env = _env_with_overlay(overlay)

    summary = push.push(root, home, env, ["hello.md"],
                        confirm=lambda p: "base", os_name="darwin")

    assert summary["written"] == ["hello.md"]
    assert summary["skipped"] == []
    assert summary["blocked"] == []
    with open(os.path.join(base_src, "hello.md"), encoding="utf-8") as fh:
        captured = fh.read()
    # machine value reverse-substituted back to ${CODE_ROOT}
    assert captured == "root is ${CODE_ROOT} now\n"


def test_unknown_file_with_purity_term_steered_to_overlay(tmp_path):
    root = str(tmp_path / "repo")
    home = str(tmp_path / "home")
    overlay = str(tmp_path / "overlay")
    os.makedirs(overlay, exist_ok=True)
    # empty manifest -> file is unknown
    _write(config.manifest_path(root), json.dumps({"items": []}))
    # the purity denylist comes from the local .ccpkg/purity-terms.txt
    _write(os.path.join(root, ".ccpkg", "purity-terms.txt"), "acmecorp\ngadgetpro\n")
    _write(os.path.join(home, "agents/profile.md"),
           "I work at acmecorp on gadgetpro.\n")
    env = _env_with_overlay(overlay)
    seen = {}

    def confirm(suggestion):
        # push passes the steered suggestion through; honor it.
        seen["suggestion"] = suggestion
        return suggestion

    summary = push.push(root, home, env, ["agents/profile.md"],
                        confirm=confirm, os_name="darwin")

    assert seen["suggestion"] == "overlay"
    assert summary["written"] == ["agents/profile.md"]
    # written into OVERLAY_DIR, never into the base source tree.
    assert os.path.isfile(os.path.join(overlay, "agents/profile.md"))
    assert not os.path.exists(
        os.path.join(config.home_claude_src(root), "agents/profile.md"))


def test_file_with_secret_is_blocked(tmp_path):
    root = str(tmp_path / "repo")
    home = str(tmp_path / "home")
    overlay = str(tmp_path / "overlay")
    os.makedirs(overlay, exist_ok=True)
    _write(
        config.manifest_path(root),
        json.dumps({"items": [{"path": "creds.md", "mode": "template",
                               "os": "any", "layer": "base"}]}),
    )
    base_src = config.home_claude_src(root)
    _write(os.path.join(base_src, "creds.md"), "placeholder\n")
    _write(os.path.join(home, "creds.md"),
           "token sk-ABCDEFGHIJKLMNOPQRSTUVWX\n")
    env = _env_with_overlay(overlay)

    summary = push.push(root, home, env, ["creds.md"],
                        confirm=lambda p: "base", os_name="darwin")

    assert summary["written"] == []
    assert summary["blocked"] == ["creds.md"]
    # repo file must be untouched by a blocked write.
    with open(os.path.join(base_src, "creds.md"), encoding="utf-8") as fh:
        assert fh.read() == "placeholder\n"


def test_unchanged_file_is_skipped(tmp_path):
    root = str(tmp_path / "repo")
    home = str(tmp_path / "home")
    overlay = str(tmp_path / "overlay")
    os.makedirs(overlay, exist_ok=True)
    _write(
        config.manifest_path(root),
        json.dumps({"items": [{"path": "same.md", "mode": "template",
                               "os": "any", "layer": "base"}]}),
    )
    base_src = config.home_claude_src(root)
    # repo holds the templated form; home holds the expanded form; rendering home
    # back to ${VAR} equals the repo content -> no diff -> skipped.
    _write(os.path.join(base_src, "same.md"), "root ${CODE_ROOT}\n")
    _write(os.path.join(home, "same.md"),
           "root /Users/example/Documents/Code\n")
    env = _env_with_overlay(overlay)

    summary = push.push(root, home, env, ["same.md"],
                        confirm=lambda p: "base", os_name="darwin")

    assert summary["written"] == []
    assert summary["skipped"] == ["same.md"]
    assert summary["blocked"] == []
