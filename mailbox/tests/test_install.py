import importlib
import json
import os
import sys

import pytest


@pytest.fixture
def fake_repo(tmp_path):
    """A fake checkout with bin/mailbox + hooks/, plus install.py importable."""
    repo = tmp_path / "repo"
    (repo / "bin").mkdir(parents=True)
    (repo / "hooks").mkdir(parents=True)
    (repo / "bin" / "mailbox").write_text("#!/bin/sh\nexec python3 -m mailbox.cli \"$@\"\n")
    for name in (
        "session_start.py",
        "pre_tool_use.py",
        "post_tool_use.py",
        "user_prompt_submit.py",
        "session_end.py",
    ):
        (repo / "hooks" / name).write_text("# hook\n")
    # Copy the real install.py into the fake repo so repo_root resolves there.
    real_install = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "install.py"
    )
    with open(real_install) as f:
        (repo / "install.py").write_text(f.read())
    return repo


@pytest.fixture
def install_mod(fake_repo, monkeypatch, tmp_path):
    """Import the copied install.py as a module, with MAILBOX_HOME under a temp ~/.claude."""
    claude_dir = tmp_path / "dot_claude"
    home = claude_dir / "mailbox"
    monkeypatch.setenv("MAILBOX_HOME", str(home))
    monkeypatch.setenv("MAILBOX_SOCKET", str(home / "mailboxd.sock"))
    # Make the real src package importable for `import config`-style resolution.
    repo_src = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
    )
    monkeypatch.syspath_prepend(repo_src)
    monkeypatch.syspath_prepend(str(fake_repo))
    sys.modules.pop("install", None)
    mod = importlib.import_module("install")
    importlib.reload(mod)
    return mod, str(home), str(claude_dir)


def _seed_settings(claude_dir):
    os.makedirs(claude_dir, exist_ok=True)
    settings = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "python3 ~/.claude/daemon/notify.py"}
                    ],
                }
            ]
        }
    }
    with open(os.path.join(claude_dir, "settings.json"), "w") as f:
        json.dump(settings, f)


def _read_settings(claude_dir):
    with open(os.path.join(claude_dir, "settings.json")) as f:
        return json.load(f)


def _all_commands(event_groups):
    cmds = []
    for group in event_groups:
        for h in group.get("hooks", []):
            cmds.append(h.get("command", ""))
    return cmds


def test_install_idempotent_preserves_notify_hook(install_mod, fake_repo):
    mod, home, claude_dir = install_mod
    _seed_settings(claude_dir)

    rc1 = mod.main()
    assert rc1 == 0
    rc2 = mod.main()
    assert rc2 == 0

    # Symlinks exist and point at the fake repo.
    bin_link = os.path.join(home, "mailbox")
    hooks_link = os.path.join(home, "hooks")
    assert os.path.islink(bin_link)
    assert os.path.realpath(bin_link) == os.path.realpath(str(fake_repo / "bin" / "mailbox"))
    assert os.path.islink(hooks_link)
    assert os.path.realpath(hooks_link) == os.path.realpath(str(fake_repo / "hooks"))

    settings = _read_settings(claude_dir)
    hooks = settings["hooks"]

    # All five events wired.
    for event in ("SessionStart", "PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionEnd"):
        assert event in hooks, "missing event: " + event

    # The pre-existing notify hook is preserved on PostToolUse.
    post_cmds = _all_commands(hooks["PostToolUse"])
    assert "python3 ~/.claude/daemon/notify.py" in post_cmds

    # Mailbox hooks appear exactly once per event (idempotent after two runs).
    expected = {
        "SessionStart": "session_start.py",
        "PreToolUse": "pre_tool_use.py",
        "PostToolUse": "post_tool_use.py",
        "UserPromptSubmit": "user_prompt_submit.py",
        "SessionEnd": "session_end.py",
    }
    for event, filename in expected.items():
        cmds = _all_commands(hooks[event])
        mailbox_cmds = [c for c in cmds if "mailbox/hooks/" + filename in c]
        assert len(mailbox_cmds) == 1, (
            "event " + event + " mailbox cmds: " + repr(mailbox_cmds)
        )
        assert mailbox_cmds[0] == "python3 " + os.path.join(home, "hooks", filename)

    # PreToolUse mailbox group carries the write-tool matcher.
    pre_group = [
        g for g in hooks["PreToolUse"]
        if any("pre_tool_use.py" in h.get("command", "") for h in g.get("hooks", []))
    ][0]
    assert pre_group["matcher"] == "Edit|Write|MultiEdit|NotebookEdit"
