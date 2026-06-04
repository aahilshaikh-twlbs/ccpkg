import json
import os
import sys

import pytest

from ccpkg import mailbox_install


# ---- helpers ---------------------------------------------------------------

HOOK_SCRIPTS = {
    "UserPromptSubmit": (None, "user_prompt_submit.py"),
    "PostToolUse": ("*", "post_tool_use.py"),
    "SessionStart": (None, "session_start.py"),
    "PreToolUse": ("Edit|Write|MultiEdit|NotebookEdit", "pre_tool_use.py"),
    "SessionEnd": (None, "session_end.py"),
}


def make_vendored_mailbox(root, with_installer=True):
    """Build a minimal fake vendored mailbox/ tree under `root`."""
    mb = os.path.join(root, "mailbox")
    os.makedirs(os.path.join(mb, "bin"), exist_ok=True)
    os.makedirs(os.path.join(mb, "hooks"), exist_ok=True)
    # the coordinator entrypoint the `mailbox` symlink targets
    with open(os.path.join(mb, "bin", "mailbox"), "w") as fh:
        fh.write("#!/usr/bin/env python3\nprint('mailbox')\n")
    for _evt, (_m, script) in HOOK_SCRIPTS.items():
        with open(os.path.join(mb, "hooks", script), "w") as fh:
            fh.write("#!/usr/bin/env python3\n")
    if with_installer:
        # stub vendored installer: importing it must not run anything,
        # and calling install(home_target) records that it was used.
        with open(os.path.join(mb, "install.py"), "w") as fh:
            fh.write(
                "def install(home_target):\n"
                "    import os\n"
                "    marker = os.path.join(home_target, '.vendored_install_ran')\n"
                "    with open(marker, 'w') as f:\n"
                "        f.write(home_target)\n"
                "    return {'vendored': 'ok'}\n"
            )
    return mb


# ---- mailbox_src -----------------------------------------------------------

def test_mailbox_src_joins_root(tmp_path):
    root = str(tmp_path)
    assert mailbox_install.mailbox_src(root) == os.path.join(root, "mailbox")


# ---- preferred path: import the vendored installer -------------------------

def test_install_prefers_vendored_installer(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    make_vendored_mailbox(root, with_installer=True)

    status = mailbox_install.install(root, tmp_home)

    assert isinstance(status, dict)
    assert status["mailbox"] == "ok"
    assert status["mode"] == "vendored"
    # the vendored installer was actually invoked with our home target
    marker = os.path.join(tmp_home, ".vendored_install_ran")
    assert os.path.isfile(marker)
    with open(marker) as fh:
        assert fh.read() == tmp_home
    # importing the vendored module must not pollute sys.modules permanently
    assert "ccpkg_vendored_mailbox_install" not in sys.modules


# ---- fallback path: built-in symlink + merge -------------------------------

def test_install_fallback_creates_symlinks_and_merges_hooks(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    mb = make_vendored_mailbox(root, with_installer=False)

    status = mailbox_install.install(root, tmp_home)

    assert status["mailbox"] == "ok"
    assert status["mode"] == "builtin"

    # symlinks created under ~/.claude/mailbox/{mailbox,hooks}
    link_mailbox = os.path.join(tmp_home, "mailbox", "mailbox")
    link_hooks = os.path.join(tmp_home, "mailbox", "hooks")
    assert os.path.islink(link_mailbox)
    assert os.path.islink(link_hooks)
    assert os.path.realpath(link_mailbox) == os.path.realpath(
        os.path.join(mb, "bin", "mailbox")
    )
    assert os.path.realpath(link_hooks) == os.path.realpath(
        os.path.join(mb, "hooks")
    )

    # settings.json now carries all 5 hooks, $HOME-relative
    settings = json.load(open(os.path.join(tmp_home, "settings.json")))
    hooks = settings["hooks"]
    seen = {}
    for evt, groups in hooks.items():
        for grp in groups:
            for hk in grp["hooks"]:
                seen[(evt, grp.get("matcher"))] = hk["command"]
    for evt, (matcher, script) in HOOK_SCRIPTS.items():
        cmd = seen[(evt, matcher)]
        assert cmd == 'python3 "$HOME/.claude/mailbox/hooks/%s"' % script
        assert "/Users/" not in cmd
        assert "/home/" not in cmd


def test_install_fallback_preserves_existing_settings_and_backs_up(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    make_vendored_mailbox(root, with_installer=False)

    # pre-existing settings with an unrelated key and an unrelated hook event
    existing = {
        "model": "opus",
        "hooks": {"Notification": [{"hooks": [{"type": "command", "command": "echo hi"}]}]},
    }
    settings_path = os.path.join(tmp_home, "settings.json")
    with open(settings_path, "w") as fh:
        json.dump(existing, fh)

    mailbox_install.install(root, tmp_home)

    settings = json.load(open(settings_path))
    # unrelated top-level key preserved
    assert settings["model"] == "opus"
    # unrelated hook event preserved
    assert settings["hooks"]["Notification"][0]["hooks"][0]["command"] == "echo hi"
    # mailbox hooks added
    assert "SessionStart" in settings["hooks"]
    # a backup of the prior settings was written
    assert os.path.isfile(settings_path + ".ccpkg.bak")


def test_install_is_idempotent(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    make_vendored_mailbox(root, with_installer=False)

    first = mailbox_install.install(root, tmp_home)
    settings_after_first = json.load(open(os.path.join(tmp_home, "settings.json")))
    second = mailbox_install.install(root, tmp_home)
    settings_after_second = json.load(open(os.path.join(tmp_home, "settings.json")))

    assert first["mailbox"] == "ok"
    assert second["mailbox"] == "ok"
    # converges: no duplicate hook groups, identical settings
    assert settings_after_first == settings_after_second
    for evt, groups in settings_after_second["hooks"].items():
        # at most one group per matcher for the mailbox events
        matchers = [g.get("matcher") for g in groups]
        assert len(matchers) == len(set(matchers))


# ---- never raises ----------------------------------------------------------

def test_install_missing_mailbox_does_not_raise(tmp_home, tmp_path):
    root = str(tmp_path / "empty_repo")
    os.makedirs(root, exist_ok=True)  # no mailbox/ subdir at all

    status = mailbox_install.install(root, tmp_home)

    assert isinstance(status, dict)
    assert status["mailbox"] == "error"
    assert "detail" in status


def test_install_vendored_installer_failure_falls_back(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    mb = make_vendored_mailbox(root, with_installer=True)
    # overwrite the vendored installer so its install() raises
    with open(os.path.join(mb, "install.py"), "w") as fh:
        fh.write("def install(home_target):\n    raise RuntimeError('boom')\n")

    status = mailbox_install.install(root, tmp_home)

    # vendored attempt failed -> fell back to builtin, still succeeded
    assert status["mailbox"] == "ok"
    assert status["mode"] == "builtin"
    assert os.path.islink(os.path.join(tmp_home, "mailbox", "hooks"))
