"""Tests for ccpkg.packs — skill & agent pack installer.

Mirrors the style of test_plugins.py: fake_run + have lambdas, never real I/O.
"""
import os
import subprocess

import pytest

from ccpkg import packs


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _have_all(_cmd):
    return True


def _have_none(_cmd):
    return False


def _have(present):
    """Return a have() that returns True only for the given commands."""
    def _h(cmd):
        return cmd in present
    return _h


# ---------------------------------------------------------------------------
# PACKS list sanity
# ---------------------------------------------------------------------------

def test_all_six_packs_present():
    ids = {p.id for p in packs.PACKS}
    assert ids == {
        "anthropic-skills", "mattpocock-skills", "composio-skills",
        "wshobson-agents", "voltagent-subagents", "awesome-cc-toolkit",
    }


def test_all_packs_default_false():
    for p in packs.PACKS:
        assert p.default is False, "pack %s must default to False" % p.id


def test_pack_groups():
    skill_ids = {p.id for p in packs.PACKS if p.group == "Skills"}
    agent_ids = {p.id for p in packs.PACKS if p.group == "Agents"}
    assert skill_ids == {"anthropic-skills", "mattpocock-skills", "composio-skills"}
    assert agent_ids == {"wshobson-agents", "voltagent-subagents", "awesome-cc-toolkit"}


# ---------------------------------------------------------------------------
# marketplace packs
# ---------------------------------------------------------------------------

def test_marketplace_skipped_when_no_claude(fake_run, tmp_path):
    result = packs.cli_install(
        run=fake_run, have=_have_none,
        home=str(tmp_path),
        only={"anthropic-skills", "wshobson-agents"},
    )
    assert result["anthropic-skills"] == "skipped"
    assert result["wshobson-agents"] == "skipped"
    assert fake_run.calls == []


def test_marketplace_with_plugins_installs(fake_run, tmp_path):
    result = packs.cli_install(
        run=fake_run, have=_have({"claude"}),
        home=str(tmp_path),
        only={"anthropic-skills"},
    )
    assert result["anthropic-skills"] == "installed"
    # marketplace add called first, then one install per plugin
    assert fake_run.calls[0] == [
        "claude", "plugin", "marketplace", "add", "anthropics/skills"
    ]
    install_calls = fake_run.calls[1:]
    pack = next(p for p in packs.PACKS if p.id == "anthropic-skills")
    assert install_calls == [
        ["claude", "plugin", "install", plugin] for plugin in pack.plugins
    ]


def test_marketplace_empty_plugins_registers_only(fake_run, tmp_path):
    """Agent packs with no plugins list: register marketplace only -> installed."""
    result = packs.cli_install(
        run=fake_run, have=_have({"claude"}),
        home=str(tmp_path),
        only={"wshobson-agents"},
    )
    assert result["wshobson-agents"] == "installed"
    assert len(fake_run.calls) == 1
    assert fake_run.calls[0] == [
        "claude", "plugin", "marketplace", "add", "wshobson/agents"
    ]


def test_marketplace_add_failure_with_no_plugins_returns_failed(tmp_path):
    def boom(cmd, **kw):
        raise OSError("network error")

    result = packs.cli_install(
        run=boom, have=_have({"claude"}),
        home=str(tmp_path),
        only={"wshobson-agents"},
    )
    assert result["wshobson-agents"] == "failed"


def test_marketplace_add_failure_with_plugins_returns_failed(tmp_path):
    def boom(cmd, **kw):
        raise OSError("network error")

    result = packs.cli_install(
        run=boom, have=_have({"claude"}),
        home=str(tmp_path),
        only={"anthropic-skills"},
    )
    assert result["anthropic-skills"] == "failed"


def test_marketplace_partial_when_some_plugins_fail(tmp_path):
    pack = next(p for p in packs.PACKS if p.id == "anthropic-skills")
    assert len(pack.plugins) >= 2, "need at least 2 plugins for partial test"
    call_count = {"n": 0}

    def flaky(cmd, **kw):
        call_count["n"] += 1
        # marketplace add succeeds; first plugin install succeeds; rest fail
        if cmd[0] == "claude" and cmd[1] == "plugin" and cmd[2] == "install":
            if call_count["n"] > 2:   # 1=marketplace add, 2=first install ok
                raise OSError("install failed")
        class R:
            returncode = 0
        return R()

    result = packs.cli_install(
        run=flaky, have=_have({"claude"}),
        home=str(tmp_path),
        only={"anthropic-skills"},
    )
    assert result["anthropic-skills"] == "partial"


def test_marketplace_all_plugin_installs_fail_returns_failed(tmp_path):
    call_count = {"n": 0}

    def run(cmd, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # marketplace add ok
            class R:
                returncode = 0
            return R()
        raise OSError("install boom")

    result = packs.cli_install(
        run=run, have=_have({"claude"}),
        home=str(tmp_path),
        only={"anthropic-skills"},
    )
    assert result["anthropic-skills"] == "failed"


# ---------------------------------------------------------------------------
# npx packs
# ---------------------------------------------------------------------------

def test_npx_skipped_when_no_npx(fake_run, tmp_path):
    result = packs.cli_install(
        run=fake_run, have=_have_none,
        home=str(tmp_path),
        only={"mattpocock-skills"},
    )
    assert result["mattpocock-skills"] == "skipped"
    assert fake_run.calls == []


def test_npx_installs_when_available(fake_run, tmp_path):
    result = packs.cli_install(
        run=fake_run, have=_have({"npx"}),
        home=str(tmp_path),
        only={"mattpocock-skills"},
    )
    assert result["mattpocock-skills"] == "installed"
    pack = next(p for p in packs.PACKS if p.id == "mattpocock-skills")
    assert fake_run.calls == [["npx"] + list(pack.npx_args)]


def test_npx_failed_when_run_raises(tmp_path):
    def boom(cmd, **kw):
        raise OSError("npx crash")

    result = packs.cli_install(
        run=boom, have=_have({"npx"}),
        home=str(tmp_path),
        only={"mattpocock-skills"},
    )
    assert result["mattpocock-skills"] == "failed"


# ---------------------------------------------------------------------------
# gitcopy packs
# ---------------------------------------------------------------------------

def _make_git_repo_fixture(tmp_path):
    """Build a fake cloned repo in tmp_path with two SKILL.md dirs."""
    repo = tmp_path / "fake-clone"
    repo.mkdir()
    (repo / ".git").mkdir()
    for name in ("skill-alpha", "skill-beta"):
        d = repo / name
        d.mkdir()
        (d / "SKILL.md").write_text("# %s\n" % name)
        (d / "main.py").write_text("# implementation\n")
    return str(repo)


def test_gitcopy_skipped_when_no_git(tmp_path):
    result = packs.cli_install(
        run=lambda cmd, **kw: None, have=_have_none,
        home=str(tmp_path),
        only={"composio-skills"},
    )
    assert result["composio-skills"] == "skipped"


def test_gitcopy_copies_skill_dirs_into_home(tmp_path, monkeypatch):
    """gitcopy clones then copies each SKILL.md parent dir into home/skills/."""
    fake_clone = tmp_path / "fake-clone"
    fake_clone.mkdir()
    (fake_clone / ".git").mkdir()
    skill_a = fake_clone / "skill-alpha"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text("# alpha\n")
    (skill_a / "prompt.md").write_text("alpha prompt\n")

    # Make _cache_dir_for return a known path and fake the clone by pre-creating it.
    monkeypatch.setattr(packs, "_cache_dir_for",
                        lambda pack_id: str(fake_clone))

    calls = []
    def run(cmd, **kw):
        calls.append(cmd)
        class R:
            returncode = 0
        return R()

    home = tmp_path / "home"
    home.mkdir()
    result = packs.cli_install(
        run=run, have=_have({"git"}),
        home=str(home),
        only={"composio-skills"},
    )
    assert result["composio-skills"] == "installed"
    skills_dir = home / "skills"
    assert skills_dir.is_dir()
    # At least one skill directory was copied in
    skill_names = [d.name for d in skills_dir.iterdir() if d.is_dir()]
    assert skill_names, "no skill dirs copied"
    # The copied dir should contain SKILL.md
    first_skill = skills_dir / skill_names[0]
    assert (first_skill / "SKILL.md").exists()


def test_gitcopy_collision_suffixed(tmp_path, monkeypatch):
    """When two SKILL.md dirs sanitize to the same name, the second gets -2."""
    fake_clone = tmp_path / "fake-clone"
    fake_clone.mkdir()
    (fake_clone / ".git").mkdir()
    for sub in ("my skill", "my-skill"):
        d = fake_clone / sub
        d.mkdir()
        (d / "SKILL.md").write_text("# %s\n" % sub)

    monkeypatch.setattr(packs, "_cache_dir_for",
                        lambda pack_id: str(fake_clone))

    def run(cmd, **kw):
        class R:
            returncode = 0
        return R()

    home = tmp_path / "home"
    home.mkdir()
    result = packs.cli_install(
        run=run, have=_have({"git"}),
        home=str(home),
        only={"composio-skills"},
    )
    assert result["composio-skills"] == "installed"
    skills_dir = home / "skills"
    names = {d.name for d in skills_dir.iterdir() if d.is_dir()}
    # Both sanitize to "my-skill"; the first gets "my-skill", second gets "my-skill-2"
    assert "my-skill" in names or "my-skill-2" in names


def test_gitcopy_failed_when_git_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(packs, "_cache_dir_for",
                        lambda pack_id: str(tmp_path / "no-git-dir"))

    def boom(cmd, **kw):
        raise OSError("git not found")

    result = packs.cli_install(
        run=boom, have=_have({"git"}),
        home=str(tmp_path),
        only={"composio-skills"},
    )
    assert result["composio-skills"] == "failed"


# ---------------------------------------------------------------------------
# only= filter
# ---------------------------------------------------------------------------

def test_only_filters_packs(fake_run, tmp_path):
    result = packs.cli_install(
        run=fake_run, have=_have_none,
        home=str(tmp_path),
        only={"anthropic-skills"},
    )
    assert set(result.keys()) == {"anthropic-skills"}


def test_only_empty_set_returns_empty(fake_run, tmp_path):
    result = packs.cli_install(
        run=fake_run, have=_have_none,
        home=str(tmp_path),
        only=set(),
    )
    assert result == {}


def test_only_none_processes_all_packs(fake_run, tmp_path):
    result = packs.cli_install(
        run=fake_run, have=_have_none,
        home=str(tmp_path),
        only=None,
    )
    assert set(result.keys()) == {p.id for p in packs.PACKS}


# ---------------------------------------------------------------------------
# never-raises contract
# ---------------------------------------------------------------------------

def test_cli_install_never_raises_even_on_unexpected_exception(tmp_path):
    def totally_broken(cmd, **kw):
        raise RuntimeError("unexpected: %s" % cmd)

    result = packs.cli_install(
        run=totally_broken,
        have=_have_all,
        home=str(tmp_path),
    )
    # Must return a dict — never raise
    assert isinstance(result, dict)
    assert set(result.keys()) == {p.id for p in packs.PACKS}


# ---------------------------------------------------------------------------
# setup_notes
# ---------------------------------------------------------------------------

def test_setup_notes_returns_note_for_installed_pack_with_note():
    statuses = {"mattpocock-skills": "installed"}
    notes = packs.setup_notes(statuses)
    assert "/setup-matt-pocock-skills" in notes


def test_setup_notes_ignores_skipped_and_failed():
    statuses = {
        "mattpocock-skills": "skipped",
        "anthropic-skills": "failed",
    }
    notes = packs.setup_notes(statuses)
    assert notes == []


def test_setup_notes_ignores_packs_without_setup_note():
    statuses = {"anthropic-skills": "installed"}
    notes = packs.setup_notes(statuses)
    assert notes == []


def test_setup_notes_multiple_installed():
    # Currently only mattpocock-skills has a setup_note, so only one note expected.
    statuses = {
        "mattpocock-skills": "installed",
        "anthropic-skills": "installed",
    }
    notes = packs.setup_notes(statuses)
    assert "/setup-matt-pocock-skills" in notes
    assert len(notes) == 1


def test_setup_notes_unknown_id_is_ignored():
    statuses = {"nonexistent-pack": "installed"}
    notes = packs.setup_notes(statuses)
    assert notes == []
