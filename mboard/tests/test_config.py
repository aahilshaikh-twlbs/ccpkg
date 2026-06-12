import os

from mboard import config


def test_home_default(monkeypatch):
    monkeypatch.delenv("MBOARD_HOME", raising=False)
    assert config.home() == os.path.expanduser("~/.claude/mboard")


def test_home_env_override(monkeypatch):
    monkeypatch.setenv("MBOARD_HOME", "/tmp/mbx")
    assert config.home() == "/tmp/mbx"


def test_state_dir(monkeypatch):
    monkeypatch.setenv("MBOARD_HOME", "/tmp/mbx")
    assert config.state_dir() == "/tmp/mbx/state"


def test_socket_path_default(monkeypatch):
    monkeypatch.setenv("MBOARD_HOME", "/tmp/mbx")
    monkeypatch.delenv("MBOARD_SOCKET", raising=False)
    assert config.socket_path() == "/tmp/mbx/mboardd.sock"


def test_socket_path_env_override(monkeypatch):
    monkeypatch.setenv("MBOARD_HOME", "/tmp/mbx")
    monkeypatch.setenv("MBOARD_SOCKET", "/tmp/other.sock")
    assert config.socket_path() == "/tmp/other.sock"


def test_pidfile(monkeypatch):
    monkeypatch.setenv("MBOARD_HOME", "/tmp/mbx")
    assert config.pidfile() == "/tmp/mbx/mboardd.pid"


def test_logfile(monkeypatch):
    monkeypatch.setenv("MBOARD_HOME", "/tmp/mbx")
    assert config.logfile() == "/tmp/mbx/mboardd.log"


def test_constants():
    assert config.HEARTBEAT_STALE_SECONDS == 90
    assert config.AUTO_CLAIM_TTL_SECONDS == 300
    assert config.EXPLICIT_CLAIM_TTL_SECONDS == 86400
    assert config.OFFLINE_GRACE_SECONDS == 180
    assert config.MESSAGE_RETENTION_SECONDS == 3600
    assert config.PRESENCE_RETENTION_SECONDS == 86400
    assert config.WRITE_TOOLS == ("Edit", "Write", "MultiEdit", "NotebookEdit")
    assert config.SOCKET_TIMEOUT_SECONDS == 5
    assert config.SPAWN_WAIT_SECONDS == 5
