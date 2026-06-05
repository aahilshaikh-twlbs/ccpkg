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


def test_repo_root_dev_fallback_when_no_env(monkeypatch):
    monkeypatch.delenv("CCPKG_ROOT", raising=False)
    root = config.repo_root()
    # dev fallback: the dir two up from ccpkg/config.py contains manifest.json
    assert os.path.isfile(os.path.join(root, "manifest.json"))
    assert config.is_packaged() is False


def test_repo_root_uses_ccpkg_root_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("CCPKG_ROOT", str(tmp_path))
    assert config.repo_root() == str(tmp_path)
    assert config.is_packaged() is True


def test_repo_root_ignores_nonexistent_ccpkg_root(monkeypatch, tmp_path):
    bogus = os.path.join(str(tmp_path), "does-not-exist")
    monkeypatch.setenv("CCPKG_ROOT", bogus)
    # falls back to dev root; not treated as packaged
    assert config.repo_root() != bogus
    assert config.is_packaged() is False


def test_localenv_explicit_override_wins(monkeypatch, tmp_path):
    target = os.path.join(str(tmp_path), "custom.env")
    monkeypatch.setenv("CCPKG_LOCAL_ENV", target)
    assert config.localenv_path("/any/root") == target


def test_localenv_prefers_existing_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("CCPKG_LOCAL_ENV", raising=False)
    xdg = os.path.join(str(tmp_path), "xdg")
    monkeypatch.setenv("XDG_CONFIG_HOME", xdg)
    os.makedirs(os.path.join(xdg, "ccpkg"))
    xdg_env = os.path.join(xdg, "ccpkg", "local.env")
    with open(xdg_env, "w") as fh:
        fh.write("CODE_ROOT=/x\n")
    assert config.localenv_path(str(tmp_path)) == xdg_env


def test_localenv_dev_fallback_when_repo_file_exists(monkeypatch, tmp_path):
    monkeypatch.delenv("CCPKG_LOCAL_ENV", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", os.path.join(str(tmp_path), "empty-xdg"))
    monkeypatch.delenv("CCPKG_ROOT", raising=False)
    repo_env = os.path.join(str(tmp_path), "local.env")
    with open(repo_env, "w") as fh:
        fh.write("CODE_ROOT=/y\n")
    assert config.localenv_path(str(tmp_path)) == repo_env


def test_localenv_default_packaged_is_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("CCPKG_LOCAL_ENV", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", os.path.join(str(tmp_path), "xdg"))
    monkeypatch.setenv("CCPKG_ROOT", str(tmp_path))  # packaged
    # nothing exists yet -> packaged default is the XDG path
    expected = os.path.join(str(tmp_path), "xdg", "ccpkg", "local.env")
    assert config.localenv_path(str(tmp_path)) == expected
