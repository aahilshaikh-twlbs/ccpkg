import os
import shutil
import subprocess
import sys

import ccpkg.config as config

REPO_ROOT = config.repo_root()
HOOK_SRC = os.path.join(REPO_ROOT, ".githooks", "pre-commit")


def _git(repo, *args):
    return subprocess.run(
        ["git"] + list(args),
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def _make_repo(tmp_path):
    """A self-contained git repo carrying a copy of the ccpkg package, the
    .githooks dir, and a home/.claude base tree. ccpkg scan run with cwd=repo
    resolves repo_root() to this repo and scans its base files."""
    repo = str(tmp_path / "repo")
    os.makedirs(repo)
    # vendor a copy of the real ccpkg package so `python3 -m ccpkg` works here
    shutil.copytree(os.path.join(REPO_ROOT, "ccpkg"), os.path.join(repo, "ccpkg"))
    # copy the hook under test
    os.makedirs(os.path.join(repo, ".githooks"))
    shutil.copy(HOOK_SRC, os.path.join(repo, ".githooks", "pre-commit"))
    os.chmod(os.path.join(repo, ".githooks", "pre-commit"), 0o755)
    # base source tree with one clean managed file
    base = os.path.join(repo, "home", ".claude")
    os.makedirs(base)
    with open(os.path.join(base, "settings.json"), "w") as fh:
        fh.write('{"model": "opus"}\n')
    # manifest so scan_paths/cli has a base layer to walk
    with open(os.path.join(repo, "manifest.json"), "w") as fh:
        fh.write('{"items": [{"path": "settings.json", "mode": "merge", '
                 '"os": "any", "layer": "base"}]}\n')
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.test")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "core.hooksPath", ".githooks")
    return repo


def _run_hook(repo):
    """Run the pre-commit hook directly with cwd=repo and the repo on
    PYTHONPATH so `python3 -m ccpkg` imports the vendored copy."""
    env = dict(os.environ)
    env["PYTHONPATH"] = repo + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [os.path.join(repo, ".githooks", "pre-commit")],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def test_hook_is_executable():
    st = os.stat(HOOK_SRC)
    assert st.st_mode & 0o111, "pre-commit hook must be executable"


def test_clean_tree_passes(tmp_path):
    repo = _make_repo(tmp_path)
    _git(repo, "add", "-A")
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout


def test_planted_purity_term_blocks(tmp_path):
    repo = _make_repo(tmp_path)
    # the denylist term is supplied via the local .ccpkg/purity-terms.txt (the
    # public scanner ships with empty defaults). .ccpkg/ is excluded from the
    # sweep, so the term file itself is not scanned.
    ccpkg_dir = os.path.join(repo, ".ccpkg")
    os.makedirs(ccpkg_dir, exist_ok=True)
    with open(os.path.join(ccpkg_dir, "purity-terms.txt"), "w") as fh:
        fh.write("acmecorp\n")
    base_file = os.path.join(repo, "home", ".claude", "settings.json")
    with open(base_file, "w") as fh:
        fh.write('{"org": "acmecorp"}\n')
    _git(repo, "add", "-A")
    result = _run_hook(repo)
    assert result.returncode != 0, result.stdout


def test_hook_invokes_python_module():
    # contract §16: the hook must call `python3 -m ccpkg scan`
    with open(HOOK_SRC) as fh:
        body = fh.read()
    assert "-m ccpkg scan" in body
