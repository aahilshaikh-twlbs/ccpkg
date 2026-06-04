import os
import socketserver
import threading

from . import protocol


class _MailboxStreamHandler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline()
        if not line:
            return
        try:
            request = protocol.decode(line)
        except Exception as exc:  # malformed JSON on the wire
            response = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
        else:
            with self.server.engine_lock:
                response = protocol.dispatch(self.server.engine, request)
        self.wfile.write(protocol.encode(response))


class _MailboxUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path, engine, engine_lock):
        self.engine = engine
        self.engine_lock = engine_lock
        self._socket_path = socket_path
        socketserver.UnixStreamServer.__init__(
            self, socket_path, _MailboxStreamHandler
        )

    def server_bind(self):
        # Unlink any stale socket (or leftover file) before binding.
        if os.path.exists(self._socket_path):
            os.unlink(self._socket_path)
        socketserver.UnixStreamServer.server_bind(self)
        os.chmod(self._socket_path, 0o600)


class MailboxServer:
    def __init__(self, engine, socket_path):
        self.engine = engine
        self.socket_path = socket_path
        self.engine_lock = threading.Lock()
        self._server = _MailboxUnixServer(socket_path, engine, self.engine_lock)

    def serve_forever(self):
        self._server.serve_forever()

    def shutdown(self):
        self._server.shutdown()
        self._server.server_close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
