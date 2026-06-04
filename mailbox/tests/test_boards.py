import hashlib
import os
import subprocess

from mailbox.boards import board_id_for_name, derive_repo_board


def _git(*args, cwd):
    subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _make_repo(path):
    os.makedirs(path, exist_ok=True)
    _git("init", cwd=path)
    _git("config", "user.email", "t@t.t", cwd=path)
    _git("config", "user.name", "t", cwd=path)
    return path


def _repo_id(toplevel):
    return "repo-" + hashlib.sha1(toplevel.encode()).hexdigest()[:12]


def _cwd_id(cwd):
    return "cwd-" + hashlib.sha1(cwd.encode()).hexdigest()[:12]


def test_real_git_repo_returns_repo_board_and_toplevel(tmp_path):
    repo = _make_repo(str(tmp_path / "myrepo"))
    board_id, root = derive_repo_board(repo)
    # git may canonicalize the path (e.g. /private/var on macOS), so resolve.
    real_root = os.path.realpath(repo)
    assert root == real_root
    assert board_id == _repo_id(real_root)
    assert board_id.startswith("repo-")
    assert len(board_id) == len("repo-") + 12


def test_subdir_of_repo_maps_to_worktree_root(tmp_path):
    repo = _make_repo(str(tmp_path / "myrepo"))
    sub = os.path.join(repo, "a", "b")
    os.makedirs(sub, exist_ok=True)
    board_id, root = derive_repo_board(sub)
    real_root = os.path.realpath(repo)
    assert root == real_root
    assert board_id == _repo_id(real_root)


def test_non_repo_dir_falls_back_to_cwd_board(tmp_path):
    plain = str(tmp_path / "notarepo")
    os.makedirs(plain, exist_ok=True)
    board_id, root = derive_repo_board(plain)
    assert root == plain
    assert board_id == _cwd_id(plain)
    assert board_id.startswith("cwd-")
    assert len(board_id) == len("cwd-") + 12


def test_distinct_repos_get_distinct_boards(tmp_path):
    repo_a = _make_repo(str(tmp_path / "a"))
    repo_b = _make_repo(str(tmp_path / "b"))
    id_a, _ = derive_repo_board(repo_a)
    id_b, _ = derive_repo_board(repo_b)
    assert id_a != id_b


def test_board_id_for_name_basic_slug():
    assert board_id_for_name("My Feature") == "named-my-feature"


def test_board_id_for_name_collapses_and_strips_separators():
    assert board_id_for_name("  Hello___World!!  ") == "named-hello-world"
    assert board_id_for_name("--Foo--Bar--") == "named-foo-bar"


def test_board_id_for_name_lowercases_and_keeps_digits():
    assert board_id_for_name("Sprint 42 Auth") == "named-sprint-42-auth"


def test_board_id_for_name_truncates_to_40_chars():
    name = "x" * 100
    result = board_id_for_name(name)
    assert result == "named-" + "x" * 40
