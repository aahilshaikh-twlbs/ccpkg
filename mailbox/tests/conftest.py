import os

import pytest


class Clock:
    """Mutable fake clock; advance ``t`` in tests for deterministic liveness."""

    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def engine(tmp_path, clock):
    from mailbox.engine import MailboxEngine

    return MailboxEngine(str(tmp_path), now_fn=clock)


def pytest_configure(config):
    # macOS AF_UNIX sun_path is limited to 104 bytes including NUL terminator.
    # pytest's default basetemp under /private/var/folders/... is far too long
    # for a Unix socket, so we force a SHORT basetemp under /tmp. It must also be
    # UNIQUE per run: a fixed path (e.g. "/tmp/mbx-t") is reused across runs and
    # is not cleaned between them, so overlapping runs collide. Keying on the pid
    # keeps the path short (e.g. "/tmp/mbx-12345") while isolating each run.
    if not config.option.basetemp:
        config.option.basetemp = "/tmp/mbx-{}".format(os.getpid())


@pytest.fixture
def tmp_home(monkeypatch, tmp_path):
    home = tmp_path / "mbx_home"
    home.mkdir()
    sock = home / "mailboxd.sock"
    monkeypatch.setenv("MAILBOX_HOME", str(home))
    monkeypatch.setenv("MAILBOX_SOCKET", str(sock))
    # Ensure spawned subprocesses (e.g. the daemon) can find the mailbox package.
    # The stdlib has a 'mailbox' module that shadows ours unless src/ is first on PYTHONPATH.
    src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
    existing = os.environ.get("PYTHONPATH", "")
    new_pythonpath = src_dir + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_pythonpath)
    return home
