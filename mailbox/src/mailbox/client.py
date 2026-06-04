import os
import socket
import subprocess
import sys
import time

from . import config, protocol


def _connect(timeout=config.SOCKET_TIMEOUT_SECONDS):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(config.socket_path())
    except OSError:
        sock.close()
        raise
    return sock


def _recv_line(sock):
    chunks = []
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    return b"".join(chunks)


def _ping(timeout=config.SOCKET_TIMEOUT_SECONDS):
    sock = _connect(timeout=timeout)
    try:
        sock.sendall(protocol.encode({"op": "ping", "args": {}}))
        line = _recv_line(sock)
        resp = protocol.decode(line)
        return resp.get("ok") is True and resp.get("data") == "pong"
    finally:
        sock.close()


def ensure_running():
    try:
        if _ping():
            return
    except OSError:
        pass
    logpath = config.logfile()
    os.makedirs(os.path.dirname(logpath), exist_ok=True)
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or config.home()
    if not os.path.isdir(cwd):
        cwd = config.home()
        os.makedirs(cwd, exist_ok=True)
    # Ensure the child can import the `mailbox` package even when the spawning
    # process runs under the system python3 (installed/symlinked layout), where
    # the stdlib `mailbox` module would otherwise shadow this package. Derive the
    # package's parent (the `src` dir) from this file via realpath so symlinks
    # resolve back to the repo checkout.
    pkg_parent = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = pkg_parent + os.pathsep + env.get("PYTHONPATH", "")
    logfh = open(logpath, "a")
    try:
        subprocess.Popen(
            [sys.executable, "-m", "mailbox.daemon"],
            stdout=logfh,
            stderr=logfh,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=cwd,
            env=env,
        )
    finally:
        logfh.close()
    deadline = time.time() + config.SPAWN_WAIT_SECONDS
    while time.time() < deadline:
        try:
            if _ping(timeout=0.5):
                return
        except OSError:
            pass
        time.sleep(0.1)
    raise TimeoutError("mailbox daemon did not become reachable")


def request(op, args=None, session=None, autospawn=True):
    payload = {"op": op, "args": args or {}}
    try:
        try:
            sock = _connect()
        except (FileNotFoundError, ConnectionRefusedError):
            if not autospawn:
                raise
            ensure_running()
            sock = _connect()
        try:
            sock.sendall(protocol.encode(payload))
            line = _recv_line(sock)
        finally:
            sock.close()
        if not line:
            return {"ok": False, "error": "empty response from daemon"}
        return protocol.decode(line)
    except Exception as exc:
        return {"ok": False, "error": "{}: {}".format(type(exc).__name__, exc)}
