import os
import sys
import json
import time
import signal
import socket
import threading
from typing import Optional

from . import config, store
from .engine import MailboxEngine
from .server import MailboxServer


def write_pidfile():
    # type: () -> None
    now = time.time()
    info = {
        "pid": os.getpid(),
        "startedAt": int(now * 1000),
        "procStart": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        "socketPath": config.socket_path(),
        "logPath": config.logfile(),
        "statePath": config.state_dir(),
        "origin": "transient",
    }
    store.atomic_write_json(config.pidfile(), info)


def read_pidfile():
    # type: () -> Optional[dict]
    return store.read_json(config.pidfile())


def pid_alive(pid):
    # type: (int) -> bool
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _socket_responsive():
    # type: () -> bool
    # Authoritative liveness probe: try to actually talk to the daemon's
    # Unix socket. A successful connect is sufficient proof that *our* daemon
    # is listening; we additionally send a ping and look for "pong" when the
    # connection allows it. Any failure (no listener, refused, timeout, etc.)
    # means the daemon is not serving. Self-contained on purpose: we do NOT
    # import client, to keep daemon startup decoupled from the client layer.
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect(config.socket_path())
        try:
            sock.sendall(b'{"op":"ping","args":{}}\n')
            reply = sock.recv(4096)
            if reply and b"pong" not in reply:
                return False
        except OSError:
            # Connect succeeded but the ping round-trip failed; a live
            # connection is still sufficient evidence the daemon is up.
            pass
        return True
    except Exception:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def already_running():
    # type: () -> bool
    # A daemon counts as running ONLY if (a) the pidfile holds an int pid,
    # (b) that pid is alive, AND (c) the daemon socket actually accepts a
    # connection. pid_alive() alone cannot distinguish our daemon from an
    # unrelated process that recycled the PID after an unclean exit; the live
    # socket is the authoritative liveness signal. Without (c), a recycled PID
    # makes already_running() wrongly report True, main() exits without
    # starting, and client.ensure_running() then times out (wedged autospawn).
    info = read_pidfile()
    if not info:
        return False
    pid = info.get("pid")
    if not isinstance(pid, int):
        return False
    if not pid_alive(pid):
        return False
    return _socket_responsive()


def _log(logf, message):
    # type: (object, str) -> None
    try:
        logf.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + message + "\n")
        logf.flush()
    except Exception:
        pass


def main():
    # type: () -> int
    if already_running():
        try:
            with open(config.logfile(), "a") as logf:
                _log(logf, "daemon already running; exiting")
        except Exception:
            pass
        return 0

    os.makedirs(config.home(), exist_ok=True)
    os.makedirs(config.state_dir(), exist_ok=True)

    logf = open(config.logfile(), "a")
    _log(logf, "daemon starting")

    engine = MailboxEngine(config.state_dir())
    server = MailboxServer(engine, config.socket_path())
    write_pidfile()
    _log(logf, "daemon serving on " + config.socket_path())

    cleaned = []  # mutable cell; guards against double cleanup

    def _cleanup():
        # type: () -> None
        # _cleanup() can be invoked twice on signal exit (once from
        # _handle_signal, once from the finally block). Guard so the body
        # runs only once.
        if cleaned:
            return
        cleaned.append(True)
        # server.shutdown() must run in a background thread because it calls
        # socketserver.BaseServer.shutdown() which blocks until serve_forever()
        # exits. When _cleanup() is called from a signal handler (while
        # serve_forever() is paused mid-loop), a direct call would deadlock.
        # The background thread lets serve_forever() unblock (via sys.exit(0)
        # propagating SystemExit through it) so shutdown() can complete.
        try:
            t = threading.Thread(target=server.shutdown, daemon=True)
            t.start()
        except Exception:
            pass
        store.remove(config.socket_path())
        store.remove(config.pidfile())
        _log(logf, "daemon stopped")
        try:
            logf.close()
        except Exception:
            pass

    def _handle_signal(signum, frame):
        # type: (int, object) -> None
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        server.serve_forever()
    finally:
        _cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
