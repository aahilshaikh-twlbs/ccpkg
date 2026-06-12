import json
import os
import subprocess
from typing import Dict, List, Optional, Sequence

import pytest

from ccpkg import plugins


@pytest.fixture
def tmp_home(monkeypatch, tmp_path):
    """Point CLAUDE_CONFIG_DIR at a temp home target and return its path."""
    home = tmp_path / "home_claude"
    home.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    return str(home)


@pytest.fixture
def tmp_repo(tmp_path):
    """Build a minimal fake repo tree (manifest.json + home/.claude/ + a couple items).

    Returns the repo root path as a string. The tree is:
        <root>/manifest.json
        <root>/home/.claude/settings.json          (merge)
        <root>/home/.claude/statusline.sh           (symlink)
        <root>/home/.claude/settings.local.json.tmpl (template)
    """
    root = tmp_path / "repo"
    src = root / "home" / ".claude"
    src.mkdir(parents=True)

    (src / "settings.json").write_text(
        json.dumps({"model": "claude-base", "enabledPlugins": {}}, indent=2)
    )
    (src / "statusline.sh").write_text("#!/usr/bin/env bash\necho base-statusline\n")
    (src / "settings.local.json.tmpl").write_text(
        json.dumps({"awsProfile": "${AWS_PROFILE}"}, indent=2)
    )

    manifest = {
        "items": [
            {"path": "settings.json", "mode": "merge", "os": "any", "layer": "base"},
            {"path": "statusline.sh", "mode": "symlink", "os": "any", "layer": "base"},
            {
                "path": "settings.local.json.tmpl",
                "mode": "template",
                "os": "any",
                "layer": "base",
            },
        ]
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return str(root)


class _FakeRun:
    """A subprocess.run double: records calls, returns canned CompletedProcess results.

    Default result is returncode 0 with empty stdout/stderr. Queue specific results
    keyed by the first token of the command (argv[0]) via .set_result(), or set
    .default to change the fallback. Every call is appended to .calls as the raw argv.
    """

    def __init__(self):
        self.calls = []  # type: List[Sequence[str]]
        self.results = {}  # type: Dict[str, subprocess.CompletedProcess]
        self.default = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    def set_result(self, key, returncode=0, stdout="", stderr=""):
        # type: (str, int, str, str) -> None
        self.results[key] = subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=stderr
        )

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        key = ""
        if isinstance(args, (list, tuple)) and args:
            key = str(args[0])
        elif isinstance(args, str):
            key = args.split()[0] if args.split() else ""
        result = self.results.get(key, self.default)
        return subprocess.CompletedProcess(
            args=args,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def commands(self):
        # type: () -> List[Sequence[str]]
        return list(self.calls)


@pytest.fixture
def fake_run():
    """A subprocess.run replacement that records calls and never executes anything."""
    return _FakeRun()


@pytest.fixture
def e2e_repo(tmp_repo, tmp_home):
    """A tmp_repo base + sample OVERLAY_DIR + a pre-existing live settings.json.

    Returns a dict: {"root","home","overlay_dir","env"} where env is the
    localenv-shaped mapping installer.install expects (CODE_ROOT, VAULT_ROOT,
    AWS_PROFILE, OVERLAY_REPO, OVERLAY_DIR all present).
    """
    root = str(tmp_repo)
    home = str(tmp_home)
    base_src = os.path.join(root, "home", ".claude")
    os.makedirs(os.path.join(base_src, "commands"), exist_ok=True)

    # --- base source files the e2e asserts on ---
    # merge: base-managed settings keys. The base SOURCE must already carry the
    # plugin settings, because installer.install does NOT inject them (Contract
    # §12 step 5: "settings already carry enabledPlugins via base merge"). We seed
    # them via the existing plugins.ensure_plugin_settings (Contract §10) so we do
    # not hardcode (and risk drifting from) PLUGINS/MARKETPLACES.
    base_settings = plugins.ensure_plugin_settings({"model": "opus"})
    with open(os.path.join(base_src, "settings.json"), "w") as f:
        json.dump(base_settings, f, indent=2)
    # symlink: a generic command file
    with open(os.path.join(base_src, "commands", "handoff.md"), "w") as f:
        f.write("# handoff\nGeneric handoff command. No PII.\n")

    # --- minimal vendored mboard source so mboard_install.install returns a
    #     non-empty status dict (Contract §11) ---
    mboard_root = os.path.join(root, "mboard")
    os.makedirs(os.path.join(mboard_root, "bin"), exist_ok=True)
    os.makedirs(os.path.join(mboard_root, "hooks"), exist_ok=True)
    with open(os.path.join(mboard_root, "bin", "mboard"), "w") as f:
        f.write("#!/usr/bin/env bash\nexit 0\n")

    # --- base manifest (2 items, all base/any) ---
    base_manifest = {
        "items": [
            {"path": "settings.json", "mode": "merge", "os": "any", "layer": "base"},
            {"path": "commands/handoff.md", "mode": "symlink", "os": "any", "layer": "base"},
        ]
    }
    with open(os.path.join(root, "manifest.json"), "w") as f:
        json.dump(base_manifest, f, indent=2)

    # --- sample overlay dir (its own home/.claude mirror + manifest) ---
    overlay_dir = os.path.join(str(tmp_home), "..", "ccpkg_overlay")
    overlay_dir = os.path.abspath(overlay_dir)
    overlay_src = os.path.join(overlay_dir, "home", ".claude", "commands")
    os.makedirs(overlay_src, exist_ok=True)
    with open(os.path.join(overlay_dir, "home", ".claude", "commands", "private.md"), "w") as f:
        f.write("# private overlay command\n")
    overlay_manifest = {
        "items": [
            {"path": "commands/private.md", "mode": "symlink", "os": "any", "layer": "overlay"},
        ]
    }
    with open(os.path.join(overlay_dir, "manifest.json"), "w") as f:
        json.dump(overlay_manifest, f, indent=2)

    # --- pre-existing live settings.json with an UNMANAGED key ---
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "settings.json"), "w") as f:
        json.dump({"theme": "dark", "model": "sonnet"}, f, indent=2)

    env = {
        "CODE_ROOT": os.path.join(home, "Code"),
        "VAULT_ROOT": "",
        "AWS_PROFILE": "",
        "OVERLAY_REPO": "",
        "OVERLAY_DIR": overlay_dir,
    }
    return {"root": root, "home": home, "overlay_dir": overlay_dir, "env": env}
