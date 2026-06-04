import os

from ccpkg import config


def test_repo_root_is_dir_two_levels_above_config_module():
    root = config.repo_root()
    # config.py lives at <root>/ccpkg/config.py, so repo_root is two dirs up.
    expected = os.path.dirname(os.path.dirname(os.path.realpath(config.__file__)))
    assert root == expected
    assert os.path.isdir(root)
    # the ccpkg package and pyproject.toml live directly under the root.
    assert os.path.isdir(os.path.join(root, "ccpkg"))


def test_home_target_defaults_to_tilde_dot_claude(monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert config.home_target() == os.path.expanduser("~/.claude")


def test_home_target_honors_claude_config_dir(tmp_home):
    # tmp_home sets CLAUDE_CONFIG_DIR to a temp dir and returns it.
    assert config.home_target() == tmp_home


def test_home_claude_src_joins_home_dot_claude():
    assert config.home_claude_src("/x/repo") == os.path.join("/x/repo", "home", ".claude")


def test_manifest_path_joins_manifest_json():
    assert config.manifest_path("/x/repo") == os.path.join("/x/repo", "manifest.json")


def test_localenv_path_joins_local_env():
    assert config.localenv_path("/x/repo") == os.path.join("/x/repo", "local.env")


def test_backup_suffix_value():
    assert config.backup_suffix() == ".ccpkg.bak"
