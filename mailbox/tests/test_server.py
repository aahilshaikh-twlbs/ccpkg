import os
import socket
import threading
import time

import pytest

from mailbox import protocol
from mailbox.server import MailboxServer


def _send_recv(socket_path, request):
    """Connect a raw AF_UNIX socket, send one newline-framed request, read one reply."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect(socket_path)
    try:
        sock.sendall(protocol.encode(request))
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        return protocol.decode(buf)
    finally:
        sock.close()


def _start_server(engine, socket_path):
    server = MailboxServer(engine, socket_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Wait for the socket file to exist before connecting.
    deadline = time.time() + 5
    while not os.path.exists(socket_path) and time.time() < deadline:
        time.sleep(0.01)
    return server, thread


def test_socket_created_and_chmod_600(engine, tmp_path):
    socket_path = str(tmp_path / "mailboxd.sock")
    server, thread = _start_server(engine, socket_path)
    try:
        assert os.path.exists(socket_path)
        mode = os.stat(socket_path).st_mode & 0o777
        assert mode == 0o600
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_stale_socket_unlinked_on_start(engine, tmp_path):
    socket_path = str(tmp_path / "mailboxd.sock")
    # Pre-create a stale plain file at the socket path.
    with open(socket_path, "w") as f:
        f.write("stale")
    assert os.path.exists(socket_path)
    server, thread = _start_server(engine, socket_path)
    try:
        # Server must have unlinked the stale file and bound a real socket there.
        resp = _send_recv(socket_path, {"op": "ping", "args": {}})
        assert resp == {"ok": True, "data": "pong"}
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_ping_then_join_round_trip(engine, tmp_path):
    socket_path = str(tmp_path / "mailboxd.sock")
    server, thread = _start_server(engine, socket_path)
    try:
        ping_resp = _send_recv(socket_path, {"op": "ping", "args": {}})
        assert ping_resp["ok"] is True
        assert ping_resp["data"] == "pong"

        join_resp = _send_recv(
            socket_path,
            {
                "op": "join",
                "args": {
                    "session_id": "sess-a",
                    "label": "alpha",
                    "cwd": str(tmp_path),
                },
            },
        )
        assert join_resp["ok"] is True
        assert join_resp["data"]["label"] == "alpha"
        assert isinstance(join_resp["data"]["boards"], list)
        assert len(join_resp["data"]["boards"]) >= 1
        # Engine actually recorded the presence (dispatch ran under the lock).
        assert "sess-a" in engine.presence
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_unknown_op_returns_error_without_crashing(engine, tmp_path):
    socket_path = str(tmp_path / "mailboxd.sock")
    server, thread = _start_server(engine, socket_path)
    try:
        resp = _send_recv(socket_path, {"op": "nope", "args": {}})
        assert resp["ok"] is False
        assert "unknown op" in resp["error"]
        # Server still serves subsequent requests.
        assert _send_recv(socket_path, {"op": "ping", "args": {}})["data"] == "pong"
    finally:
        server.shutdown()
        thread.join(timeout=5)
