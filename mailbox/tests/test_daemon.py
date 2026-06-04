import os
import json
import signal
import socket
import subprocess
import sys
import time

from mailbox import daemon, config, protocol


def test_write_pidfile_records_self(tmp_home):
    daemon.write_pidfile()

    with open(config.pidfile(), "r") as fh:
        data = json.load(fh)

    assert data["pid"] == os.getpid()
    assert data["origin"] == "transient"
    assert data["socketPath"] == config.socket_path()
    assert data["logPath"] == config.logfile()
    assert data["statePath"] == config.state_dir()
    assert isinstance(data["startedAt"], int)
    assert isinstance(data["procStart"], str)


def test_read_pidfile_roundtrip(tmp_home):
    daemon.write_pidfile()
    data = daemon.read_pidfile()
    assert data is not None
    assert data["pid"] == os.getpid()


def test_read_pidfile_missing_returns_none(tmp_home):
    assert daemon.read_pidfile() is None


def test_read_pidfile_malformed_returns_none(tmp_home):
    os.makedirs(config.home(), exist_ok=True)
    with open(config.pidfile(), "w") as fh:
        fh.write("not json {{{")
    assert daemon.read_pidfile() is None


def test_pid_alive_true_for_self():
    assert daemon.pid_alive(os.getpid()) is True


def test_pid_alive_false_for_unused_pid():
    # PID 999999 is effectively never live on a dev machine.
    assert daemon.pid_alive(999999) is False


def test_already_running_false_when_no_pidfile(tmp_home):
    assert daemon.already_running() is False


def test_already_running_false_for_live_pid_without_socket(tmp_home):
    # PID-reuse guard: a pidfile may point at a LIVE pid that is NOT our daemon
    # (e.g. the OS recycled the pid after an unclean exit). Here we record this
    # test process's own pid (definitely alive, definitely not a mailboxd, and
    # with no listener on MAILBOX_SOCKET). pid_alive() alone would say "running",
    # but the authoritative socket probe must report not-running.
    daemon.write_pidfile()  # records this process's live pid (os.getpid())
    assert daemon.pid_alive(os.getpid()) is True  # precondition: pid is alive
    assert not os.path.exists(config.socket_path())  # precondition: no listener
    assert daemon.already_running() is False


def test_already_running_false_for_dead_pid(tmp_home):
    os.makedirs(config.home(), exist_ok=True)
    with open(config.pidfile(), "w") as fh:
        json.dump({"pid": 999999, "origin": "transient"}, fh)
    assert daemon.already_running() is False


def _repo_src_dir():
    # tests/test_daemon.py -> repo root is two levels up; src is alongside tests/
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    return os.path.join(repo_root, "src")


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_daemon_spawn_ping_and_sigterm_cleanup(tmp_home):
    child_env = dict(os.environ)
    child_env["MAILBOX_HOME"] = config.home()
    child_env["MAILBOX_SOCKET"] = config.socket_path()
    src = _repo_src_dir()
    existing = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")

    # macOS AF_UNIX sun_path is limited to 104 bytes (including NUL terminator).
    # If the socket path is too long, shorten it and update child_env only
    # (no os.environ mutation — sock_path is read from child_env directly).
    if len(child_env["MAILBOX_SOCKET"]) > 103:
        import hashlib
        _h = hashlib.md5(config.home().encode()).hexdigest()[:8]
        child_env["MAILBOX_SOCKET"] = "/tmp/mbx-" + _h + ".sock"

    proc = subprocess.Popen(
        [sys.executable, "-m", "mailbox.daemon"],
        env=child_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    try:
        sock_path = child_env["MAILBOX_SOCKET"]
        assert _wait_for(lambda: os.path.exists(sock_path), timeout=5.0), \
            "daemon did not create socket"

        # raw socket round-trip: ping -> pong
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(5.0)
        client.connect(sock_path)
        client.sendall(protocol.encode({"op": "ping", "args": {}}))
        buf = b""
        while b"\n" not in buf:
            chunk = client.recv(4096)
            if not chunk:
                break
            buf += chunk
        client.close()
        resp = protocol.decode(buf)
        assert resp == {"ok": True, "data": "pong"}

        # pidfile points at a live pid
        info = daemon.read_pidfile()
        assert info is not None
        assert daemon.pid_alive(info["pid"]) is True

        # Positive case for the PID-reuse guard: a real daemon is live AND its
        # socket answers, so already_running() must report True. Point
        # config.socket_path() at the path the daemon actually bound to (the
        # spawn step may have shortened it for the AF_UNIX length limit).
        _saved_sock = os.environ.get("MAILBOX_SOCKET")
        os.environ["MAILBOX_SOCKET"] = sock_path
        try:
            assert daemon.already_running() is True
        finally:
            if _saved_sock is None:
                os.environ.pop("MAILBOX_SOCKET", None)
            else:
                os.environ["MAILBOX_SOCKET"] = _saved_sock

        # SIGTERM -> graceful shutdown + cleanup
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5.0)

        assert _wait_for(lambda: not os.path.exists(sock_path), timeout=5.0), \
            "socket not cleaned up after SIGTERM"
        assert _wait_for(lambda: not os.path.exists(config.pidfile()), timeout=5.0), \
            "pidfile not cleaned up after SIGTERM"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5.0)
