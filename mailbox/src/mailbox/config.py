import os


def home() -> str:
    return os.environ.get("MAILBOX_HOME", os.path.expanduser("~/.claude/mailbox"))


def state_dir() -> str:
    return os.path.join(home(), "state")


def socket_path() -> str:
    return os.environ.get("MAILBOX_SOCKET", os.path.join(home(), "mailboxd.sock"))


def pidfile() -> str:
    return os.path.join(home(), "mailboxd.pid")


def logfile() -> str:
    return os.path.join(home(), "mailboxd.log")


HEARTBEAT_STALE_SECONDS = 90        # presence stale after this with no heartbeat
AUTO_CLAIM_TTL_SECONDS = 300        # auto-claim expiry (refreshed by heartbeat)
EXPLICIT_CLAIM_TTL_SECONDS = 86400  # explicit claim expiry (24h)
OFFLINE_GRACE_SECONDS = 180         # mark live->offline after 2x stale w/o heartbeat
MESSAGE_RETENTION_SECONDS = 3600    # GC read messages older than this
PRESENCE_RETENTION_SECONDS = 86400  # GC offline presence older than this
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SOCKET_TIMEOUT_SECONDS = 5
SPAWN_WAIT_SECONDS = 5
