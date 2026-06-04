import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
INSTALL_SH = os.path.join(REPO_ROOT, "install.sh")


def _run_install_sh(extra_env, cwd=None):
    env = dict(os.environ)
    env.update(extra_env)
    return subprocess.run(
        ["bash", INSTALL_SH],
        cwd=cwd or os.path.expanduser("~"),  # prove it does not depend on cwd
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def test_install_sh_exists_and_is_executable():
    assert os.path.isfile(INSTALL_SH)
    assert os.access(INSTALL_SH, os.X_OK)


def test_install_sh_starts_with_bash_shebang_and_strict_mode():
    with open(INSTALL_SH, "r") as fh:
        head = fh.read()
    assert head.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in head


def test_install_sh_dryrun_exits_zero_and_reports_plan():
    proc = _run_install_sh({"CCPKG_DRYRUN": "1"})
    assert proc.returncode == 0, proc.stdout
    # resolves the repo root regardless of the caller's cwd
    assert REPO_ROOT in proc.stdout
    # detects an os value from osenv.detect_os()
    assert ("darwin" in proc.stdout) or ("linux" in proc.stdout)
    # reports the exact command it would exec
    assert "python3 -m ccpkg install" in proc.stdout
    # does NOT actually run the installer in dry-run
    assert "DRYRUN" in proc.stdout


def test_install_sh_dryrun_does_not_attempt_package_install(tmp_path):
    # Stub the package managers + sudo on PATH so any install attempt writes a
    # sentinel file. A correct dry-run must short-circuit BEFORE ensure_deps,
    # so the sentinel must NOT exist afterward. This passes even on a machine
    # where git/python3/jq are already present (where ensure_deps would no-op),
    # and FAILS the buggy ordering where ensure_deps runs before the dry-run check
    # on a box missing a dep.
    sentinel = tmp_path / "install_attempted"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("brew", "apt-get", "sudo"):
        stub = bindir / name
        stub.write_text(
            "#!/usr/bin/env bash\n"
            'echo "$0 $*" >> "%s"\n'
            "exit 0\n" % str(sentinel)
        )
        stub.chmod(0o755)
    # Keep python3 reachable (we did NOT stub it) so detect_os still works;
    # prepend the stub dir so brew/apt-get/sudo resolve to our sentinels.
    env = {"CCPKG_DRYRUN": "1", "PATH": str(bindir) + os.pathsep + os.environ["PATH"]}
    proc = _run_install_sh(env)
    assert proc.returncode == 0, proc.stdout
    assert not sentinel.exists(), (
        "dry-run attempted a package install:\n" + sentinel.read_text()
    )


def test_install_sh_pythonpath_repo_root_makes_ccpkg_importable():
    # The script exports PYTHONPATH=<repo root>; emulate the same and confirm import works.
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO_ROOT
    proc = subprocess.run(
        [sys.executable, "-c", "import ccpkg; print('ok')"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    assert proc.returncode == 0, proc.stdout
    assert "ok" in proc.stdout


def test_install_sh_exports_pythonpath_repo_root():
    with open(INSTALL_SH, "r") as fh:
        body = fh.read()
    assert "PYTHONPATH" in body
