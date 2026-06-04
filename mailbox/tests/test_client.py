import os
import signal
import socket
import time

import pytest

from mailbox import client, config, protocol


def _read_pid():
    pidpath = config.pidfile()
    if not os.path.exists(pidpath):
        return None
    with open(pidpath) as fh:
        import json
        try:
            data = json.load(fh)
        except ValueError:
            return None
    return data.get("pid")


def _kill_daemon():
    pid = _read_pid()
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    # wait up to 5s for the process to actually exit
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.05)


def test_connect_raises_when_no_socket(tmp_home):
    with pytest.raises(OSError):
        client._connect(timeout=0.5)


def test_request_ping_autospawns_daemon(tmp_home):
    try:
        resp = client.request("ping")
        assert resp["ok"] is True
        assert resp["data"] == "pong"
        # the daemon really started: pidfile written and process alive
        pid = _read_pid()
        assert pid is not None
        os.kill(pid, 0)  # raises OSError if not alive
    finally:
        _kill_daemon()


def test_second_request_reuses_running_daemon(tmp_home):
    try:
        first = client.request("ping")
        assert first["ok"] is True
        pid_after_first = _read_pid()
        assert pid_after_first is not None

        second = client.request("ping")
        assert second["ok"] is True
        assert second["data"] == "pong"
        pid_after_second = _read_pid()
        # same daemon process — no respawn
        assert pid_after_second == pid_after_first
    finally:
        _kill_daemon()


def test_request_no_autospawn_returns_error_dict(tmp_home):
    resp = client.request("ping", autospawn=False)
    assert resp["ok"] is False
    assert "error" in resp
    assert isinstance(resp["error"], str)
    # no daemon was started
    assert _read_pid() is None
