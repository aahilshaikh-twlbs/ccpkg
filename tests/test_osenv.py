import subprocess

import pytest

from ccpkg import osenv


def test_detect_os_darwin(monkeypatch):
    monkeypatch.setattr(osenv.platform, "system", lambda: "Darwin")
    assert osenv.detect_os() == "darwin"


def test_detect_os_linux(monkeypatch):
    monkeypatch.setattr(osenv.platform, "system", lambda: "Linux")
    assert osenv.detect_os() == "linux"


def test_detect_os_other_falls_back_to_linux(monkeypatch):
    monkeypatch.setattr(osenv.platform, "system", lambda: "Windows")
    assert osenv.detect_os() == "linux"


def test_have_true(monkeypatch):
    monkeypatch.setattr(osenv.shutil, "which", lambda cmd: "/usr/bin/" + cmd)
    assert osenv.have("git") is True


def test_have_false(monkeypatch):
    monkeypatch.setattr(osenv.shutil, "which", lambda cmd: None)
    assert osenv.have("git") is False


def test_install_cmd_darwin():
    assert osenv.install_cmd("darwin", "jq") == ["brew", "install", "jq"]


def test_install_cmd_linux():
    assert osenv.install_cmd("linux", "jq") == [
        "sudo", "apt-get", "install", "-y", "jq"
    ]


def test_stat_mtime_cmd_darwin():
    assert osenv.stat_mtime_cmd("darwin", "/tmp/x") == [
        "stat", "-f", "%m", "/tmp/x"
    ]


def test_stat_mtime_cmd_linux():
    assert osenv.stat_mtime_cmd("linux", "/tmp/x") == [
        "stat", "-c", "%Y", "/tmp/x"
    ]


def test_ensure_deps_present_when_already_have(monkeypatch, fake_run):
    monkeypatch.setattr(osenv.shutil, "which", lambda cmd: "/usr/bin/" + cmd)
    result = osenv.ensure_deps("linux", ["git", "jq"], run=fake_run)
    assert result == {"git": "present", "jq": "present"}
    # nothing installed: no run calls
    assert fake_run.calls == []


def test_ensure_deps_installs_missing_darwin(monkeypatch, fake_run):
    monkeypatch.setattr(osenv.shutil, "which", lambda cmd: None)
    result = osenv.ensure_deps("darwin", ["jq"], run=fake_run)
    assert result == {"jq": "installed"}
    assert fake_run.calls == [["brew", "install", "jq"]]


def test_ensure_deps_installs_missing_linux(monkeypatch, fake_run):
    monkeypatch.setattr(osenv.shutil, "which", lambda cmd: None)
    result = osenv.ensure_deps("linux", ["jq"], run=fake_run)
    assert result == {"jq": "installed"}
    assert fake_run.calls == [["sudo", "apt-get", "install", "-y", "jq"]]


def test_ensure_deps_marks_missing_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(osenv.shutil, "which", lambda cmd: None)

    def failing_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1)

    result = osenv.ensure_deps("linux", ["jq"], run=failing_run)
    assert result == {"jq": "missing"}


def test_ensure_deps_marks_missing_on_exception_never_raises(monkeypatch):
    monkeypatch.setattr(osenv.shutil, "which", lambda cmd: None)

    def raising_run(cmd, **kwargs):
        raise OSError("brew not found")

    result = osenv.ensure_deps("darwin", ["jq"], run=raising_run)
    assert result == {"jq": "missing"}


def test_ensure_deps_mixed_present_and_installed(monkeypatch, fake_run):
    present = {"git"}
    monkeypatch.setattr(
        osenv.shutil,
        "which",
        lambda cmd: "/usr/bin/git" if cmd in present else None,
    )
    result = osenv.ensure_deps("linux", ["git", "jq"], run=fake_run)
    assert result == {"git": "present", "jq": "installed"}
    assert fake_run.calls == [["sudo", "apt-get", "install", "-y", "jq"]]
