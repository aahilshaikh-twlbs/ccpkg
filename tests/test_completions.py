import os
import shutil
import subprocess

import pytest

from ccpkg import cli
from ccpkg import completions


def _patch_resolution(monkeypatch, repo, home):
    monkeypatch.setattr(cli.config, "repo_root", lambda: repo)
    monkeypatch.setattr(cli.config, "home_target", lambda: home)


# --- command_tree: the drift guard against the live parser -------------------

def test_command_tree_has_every_verb():
    tree = completions.command_tree()
    assert set(tree) == {
        "apply", "status", "new", "push", "uninstall", "share", "completions",
        "mcp", "suggest", "score", "card", "gallery",
    }


def test_command_tree_subverbs_match_parser():
    tree = completions.command_tree()
    assert tree["status"] == ["diff", "health", "scan"]
    assert tree["new"] == ["agent", "command", "hook", "skill", "overlay"]
    assert tree["mcp"] == ["list", "add"]
    assert tree["suggest"] == ["preview"]
    assert tree["gallery"] == ["index"]
    # verbs whose positional is freeform (not a subparser) have no sub-verbs
    for verb in ("apply", "push", "uninstall", "share", "completions",
                 "score", "card"):
        assert tree[verb] == []


# --- generated scripts mention the whole tree --------------------------------

@pytest.mark.parametrize("render", [completions.zsh_script, completions.bash_script])
def test_script_mentions_every_verb_and_subverb(render):
    script = render()
    tree = completions.command_tree()
    for verb in tree:
        assert verb in script, "verb %r missing from script" % verb
    for sub in (tree["status"] + tree["new"] + tree["mcp"] + tree["suggest"]
                + tree["gallery"]):
        assert sub in script, "sub-verb %r missing from script" % sub
    for preset in completions.APPLY_PRESETS:
        assert preset in script
    for val in completions.COMPLETIONS_VALUES:
        assert val in script


def test_zsh_script_is_autoload_shaped():
    script = completions.zsh_script()
    assert script.startswith("#compdef ccpkg")
    assert "_ccpkg" in script


def test_bash_script_registers_completion():
    assert "complete -F _ccpkg ccpkg" in completions.bash_script()


# --- list_items: the dynamic feed --------------------------------------------

def test_list_items_returns_sorted_manifest_paths(tmp_repo):
    items = completions.list_items(root=tmp_repo)
    assert items == sorted(items)
    assert "settings.json" in items
    assert "statusline.sh" in items


def test_list_items_missing_manifest_is_empty(tmp_path):
    assert completions.list_items(root=str(tmp_path)) == []


# --- cli wiring --------------------------------------------------------------

def test_cli_completions_items_prints_manifest_paths(tmp_repo, tmp_home, monkeypatch, capsys):
    _patch_resolution(monkeypatch, tmp_repo, tmp_home)
    rc = cli.main(["completions", "items"])
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln]
    assert lines == sorted(lines)
    assert "settings.json" in lines


@pytest.mark.parametrize("shell,needle", [
    ("zsh", "#compdef ccpkg"),
    ("bash", "complete -F _ccpkg ccpkg"),
])
def test_cli_completions_prints_script(shell, needle, capsys):
    rc = cli.main(["completions", shell])
    assert rc == 0
    assert needle in capsys.readouterr().out


def test_cli_completions_unknown_shell_errors(capsys):
    rc = cli.main(["completions", "fish"])
    assert rc == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_cli_completions_no_arg_errors(capsys):
    rc = cli.main(["completions"])
    assert rc == 2


# --- the emitted bash script is syntactically valid --------------------------

@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")
def test_bash_script_passes_syntax_check(tmp_path):
    path = tmp_path / "ccpkg.bash"
    path.write_text(completions.bash_script())
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not on PATH")
def test_zsh_script_passes_syntax_check(tmp_path):
    path = tmp_path / "ccpkg.zsh"
    path.write_text(completions.zsh_script())
    result = subprocess.run(["zsh", "-n", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
