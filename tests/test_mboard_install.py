import json
import os
import sys

import pytest

from ccpkg import mboard_install


# ---- helpers ---------------------------------------------------------------

HOOK_SCRIPTS = {
    "UserPromptSubmit": (None, "user_prompt_submit.py"),
    "PostToolUse": ("*", "post_tool_use.py"),
    "SessionStart": (None, "session_start.py"),
    "PreToolUse": ("Edit|Write|MultiEdit|NotebookEdit", "pre_tool_use.py"),
    "SessionEnd": (None, "session_end.py"),
    "Stop": (None, "stop.py"),
}


def make_vendored_mboard(root, with_installer=True):
    """Build a minimal fake vendored mboard/ tree under `root`."""
    mb = os.path.join(root, "mboard")
    os.makedirs(os.path.join(mb, "bin"), exist_ok=True)
    os.makedirs(os.path.join(mb, "hooks"), exist_ok=True)
    # the coordinator entrypoint the `mboard` symlink targets
    with open(os.path.join(mb, "bin", "mboard"), "w") as fh:
        fh.write("#!/usr/bin/env python3\nprint('mboard')\n")
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


# ---- hook command guards a transiently-missing file ------------------------

def test_hook_command_guards_missing_file():
    # A transiently-absent hook file (e.g. mid `brew upgrade`, before the symlink
    # is repointed to the new keg) must be a silent no-op, not a non-zero exit that
    # Claude Code surfaces as "SessionEnd hook failed" / "operation blocked by
    # hook". Mirrors the notify-hook guard already in settings.json.
    cmd = mboard_install._hook_command("session_end.py")
    path = '"$HOME/.claude/mboard/hooks/session_end.py"'
    assert cmd == "[ -f %s ] && python3 %s || true" % (path, path)
    # still contains the marker the de-dupe logic keys on
    assert "mboard/hooks/" in cmd


# ---- mboard_src -----------------------------------------------------------

def test_mboard_src_joins_root(tmp_path):
    root = str(tmp_path)
    assert mboard_install.mboard_src(root) == os.path.join(root, "mboard")


# ---- preferred path: import the vendored installer -------------------------

def test_install_prefers_vendored_installer(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    make_vendored_mboard(root, with_installer=True)

    status = mboard_install.install(root, tmp_home)

    assert isinstance(status, dict)
    assert status["mboard"] == "ok"
    assert status["mode"] == "vendored"
    # the vendored installer was actually invoked with our home target
    marker = os.path.join(tmp_home, ".vendored_install_ran")
    assert os.path.isfile(marker)
    with open(marker) as fh:
        assert fh.read() == tmp_home
    # importing the vendored module must not pollute sys.modules permanently
    assert "ccpkg_vendored_mboard_install" not in sys.modules


# ---- fallback path: built-in symlink + merge -------------------------------

def test_install_fallback_creates_symlinks_and_merges_hooks(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    mb = make_vendored_mboard(root, with_installer=False)

    status = mboard_install.install(root, tmp_home)

    assert status["mboard"] == "ok"
    assert status["mode"] == "builtin"

    # symlinks created under ~/.claude/mboard/{mboard,hooks}
    link_mboard = os.path.join(tmp_home, "mboard", "mboard")
    link_hooks = os.path.join(tmp_home, "mboard", "hooks")
    assert os.path.islink(link_mboard)
    assert os.path.islink(link_hooks)
    assert os.path.realpath(link_mboard) == os.path.realpath(
        os.path.join(mb, "bin", "mboard")
    )
    assert os.path.realpath(link_hooks) == os.path.realpath(
        os.path.join(mb, "hooks")
    )

    # settings.json now carries all 6 hooks, $HOME-relative
    settings = json.load(open(os.path.join(tmp_home, "settings.json")))
    hooks = settings["hooks"]
    seen = {}
    for evt, groups in hooks.items():
        for grp in groups:
            for hk in grp["hooks"]:
                seen[(evt, grp.get("matcher"))] = hk["command"]
    for evt, (matcher, script) in HOOK_SCRIPTS.items():
        cmd = seen[(evt, matcher)]
        path = '"$HOME/.claude/mboard/hooks/%s"' % script
        assert cmd == "[ -f %s ] && python3 %s || true" % (path, path)
        assert "/Users/" not in cmd
        assert "/home/" not in cmd


def test_install_fallback_preserves_existing_settings_and_backs_up(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    make_vendored_mboard(root, with_installer=False)

    # pre-existing settings with an unrelated key and an unrelated hook event
    existing = {
        "model": "opus",
        "hooks": {"Notification": [{"hooks": [{"type": "command", "command": "echo hi"}]}]},
    }
    settings_path = os.path.join(tmp_home, "settings.json")
    with open(settings_path, "w") as fh:
        json.dump(existing, fh)

    mboard_install.install(root, tmp_home)

    settings = json.load(open(settings_path))
    # unrelated top-level key preserved
    assert settings["model"] == "opus"
    # unrelated hook event preserved
    assert settings["hooks"]["Notification"][0]["hooks"][0]["command"] == "echo hi"
    # mboard hooks added
    assert "SessionStart" in settings["hooks"]
    # a backup of the prior settings was written
    assert os.path.isfile(settings_path + ".ccpkg.bak")


def test_install_is_idempotent(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    make_vendored_mboard(root, with_installer=False)

    first = mboard_install.install(root, tmp_home)
    settings_after_first = json.load(open(os.path.join(tmp_home, "settings.json")))
    second = mboard_install.install(root, tmp_home)
    settings_after_second = json.load(open(os.path.join(tmp_home, "settings.json")))

    assert first["mboard"] == "ok"
    assert second["mboard"] == "ok"
    # converges: no duplicate hook groups, identical settings
    assert settings_after_first == settings_after_second
    for evt, groups in settings_after_second["hooks"].items():
        # at most one group per matcher for the mboard events
        matchers = [g.get("matcher") for g in groups]
        assert len(matchers) == len(set(matchers))


# ---- symlink repoint to the stable opt prefix ------------------------------

def test_ensure_symlink_repoints_to_stable_path_when_literal_differs(tmp_path):
    # Same Homebrew Cellar->opt concern as apply.apply_symlink: an existing link
    # to the versioned keg must be repointed at the stable `opt` path even though
    # both currently resolve to the same file, so `brew upgrade` can't dangle it.
    keg = tmp_path / "Cellar" / "ccpkg" / "0.1.5"
    keg.mkdir(parents=True)
    src_file = keg / "mboard"
    src_file.write_text("#!/bin/sh\n")
    opt = tmp_path / "opt" / "ccpkg"
    opt.parent.mkdir(parents=True)
    os.symlink(str(keg), str(opt))               # opt/ccpkg -> Cellar/ccpkg/0.1.5

    target = str(tmp_path / "home" / "mboard" / "mboard")
    os.makedirs(os.path.dirname(target))
    os.symlink(str(src_file), target)            # existing link -> versioned Cellar path
    stable_src = str(opt / "mboard")

    mboard_install._ensure_symlink(stable_src, target)

    assert os.readlink(target) == stable_src     # tracks the stable opt path now


# ---- never raises ----------------------------------------------------------

def test_install_missing_mboard_does_not_raise(tmp_home, tmp_path):
    root = str(tmp_path / "empty_repo")
    os.makedirs(root, exist_ok=True)  # no mboard/ subdir at all

    status = mboard_install.install(root, tmp_home)

    assert isinstance(status, dict)
    assert status["mboard"] == "error"
    assert "detail" in status


def test_install_vendored_installer_failure_falls_back(tmp_home, tmp_path):
    root = str(tmp_path / "repo")
    os.makedirs(root, exist_ok=True)
    mb = make_vendored_mboard(root, with_installer=True)
    # overwrite the vendored installer so its install() raises
    with open(os.path.join(mb, "install.py"), "w") as fh:
        fh.write("def install(home_target):\n    raise RuntimeError('boom')\n")

    status = mboard_install.install(root, tmp_home)

    # vendored attempt failed -> fell back to builtin, still succeeded
    assert status["mboard"] == "ok"
    assert status["mode"] == "builtin"
    assert os.path.islink(os.path.join(tmp_home, "mboard", "hooks"))
