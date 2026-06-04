import importlib.util
import io
import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(REPO_ROOT, "hooks")


def _load_hook(module_name, filename):
    """Load a hooks/*.py file as a standalone module (hooks are scripts, not a package)."""
    path = os.path.join(HOOKS_DIR, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_session_start_joins_and_writes_env(tmp_home, tmp_path, monkeypatch):
    from mailbox import client, config

    # Ensure a daemon is running against the temp socket (tmp_home set the paths).
    client.ensure_running()

    sid = "sess-aaaa-1111"
    cwd = str(tmp_path)
    payload = {
        "session_id": sid,
        "cwd": cwd,
        "source": "startup",
        "hook_event_name": "SessionStart",
    }

    env_file = tmp_path / "claude_env"
    env_file.write_text("")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.setenv("MAILBOX_LABEL", "alpha")
    monkeypatch.delenv("MAILBOX_BOARD", raising=False)

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    hook = _load_hook("session_start_hook", "session_start.py")
    rc = hook.main()
    assert rc == 0

    # Env file got the session id (and label) exports.
    contents = env_file.read_text()
    assert "export MAILBOX_SESSION_ID=" + sid in contents
    assert "export MAILBOX_LABEL=alpha" in contents

    # Join actually happened: whoami over the same socket sees this presence.
    resp = client.request("whoami", {"session_id": sid})
    assert resp["ok"] is True
    assert resp["data"]["exists"] is True
    assert resp["data"]["label"] == "alpha"


def test_session_start_prints_colocation(tmp_home, tmp_path, monkeypatch, capsys):
    from mailbox import client

    client.ensure_running()

    cwd = str(tmp_path)

    # First session already on the board (live).
    first = client.request(
        "join",
        {"session_id": "sess-first-0000", "label": "first",
         "cwd": cwd, "board_name": None},
    )
    assert first["ok"] is True

    sid2 = "sess-second-1111"
    payload = {
        "session_id": sid2,
        "cwd": cwd,
        "source": "startup",
        "hook_event_name": "SessionStart",
    }
    monkeypatch.setenv("MAILBOX_LABEL", "second")
    monkeypatch.delenv("MAILBOX_BOARD", raising=False)
    monkeypatch.delenv("CLAUDE_ENV_FILE", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    hook = _load_hook("session_start_hook2", "session_start.py")
    rc = hook.main()
    assert rc == 0

    out = capsys.readouterr().out
    assert "\U0001f91d Sharing " in out
    assert "first" in out
    assert "mailbox ps|claims|send|inbox" in out


import subprocess

from mailbox import client, config

SRC_DIR = os.path.join(REPO_ROOT, "src")


def tmp_path_cwd():
    """Stable directory under the temp home, used for path normalization."""
    d = os.path.join(config.home(), "work")
    os.makedirs(d, exist_ok=True)
    return d


def _run_hook(hook_name, stdin_payload):
    """Run a hook script as a subprocess; return CompletedProcess.

    Inherits MAILBOX_HOME / MAILBOX_SOCKET from the current env (set by
    tmp_home via monkeypatch.setenv, which updates os.environ in-process)
    and puts the repo src on PYTHONPATH so `import mailbox` works.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC_DIR + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, hook_name)],
        input=json.dumps(stdin_payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=20,
    )
    return proc


def test_pre_tool_use_denies_live_conflict(tmp_home):
    # Bring up the real daemon on the temp socket. (Daemon is detached and is
    # not explicitly stopped here — same inherited pattern as Task 16; each
    # test gets a fresh temp socket via tmp_home so there is no collision.)
    client.ensure_running()
    target = os.path.join(tmp_path_cwd(), "shared.py")

    # Session A joins this cwd's board and claims the file (explicit claim).
    joined = client.request("join", {
        "session_id": "sessA",
        "label": "alice",
        "cwd": tmp_path_cwd(),
    })
    assert joined["ok"] is True
    claimed = client.request("claim", {
        "session_id": "sessA",
        "globs": [target],
        "note": "refactoring",
    })
    assert claimed["ok"] is True

    # Session B also joins the same board, then the hook runs for B.
    joinedB = client.request("join", {
        "session_id": "sessB",
        "label": "bob",
        "cwd": tmp_path_cwd(),
    })
    assert joinedB["ok"] is True

    proc = _run_hook("pre_tool_use.py", {
        "session_id": "sessB",
        "cwd": tmp_path_cwd(),
        "tool_name": "Edit",
        "tool_input": {"file_path": target},
    })

    assert proc.returncode == 0
    out = proc.stdout.decode("utf-8").strip()
    assert out, "expected deny JSON on stdout, got empty"
    payload = json.loads(out)
    hso = payload["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert target in hso["permissionDecisionReason"]
    assert "alice" in hso["permissionDecisionReason"]


def test_pre_tool_use_fail_open_when_daemon_unreachable(tmp_home):
    # Safety-critical: a down/broken mailbox must NEVER block a real edit.
    # Point MAILBOX_SOCKET at an unreachable, unbindable socket path: an
    # over-length AF_UNIX path makes connect() raise a plain OSError (not
    # FileNotFoundError/ConnectionRefusedError), so client.request does not
    # autospawn and returns an error immediately — no daemon, no wait. The
    # path is also far too long for any daemon to bind, so it can never come
    # up. The hook must still exit 0 and emit NO deny JSON (fail-open).
    unreachable_sock = "/tmp/" + ("x" * 200) + ".sock"
    env = dict(os.environ)
    env["MAILBOX_SOCKET"] = unreachable_sock
    env["PYTHONPATH"] = SRC_DIR + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, "pre_tool_use.py")],
        input=json.dumps({
            "session_id": "sessFAILOPEN",
            "cwd": tmp_path_cwd(),
            "tool_name": "Edit",
            "tool_input": {"file_path": os.path.join(tmp_path_cwd(), "z.py")},
        }).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=20,
    )
    # Exit 0 (allow) and NO deny JSON on stdout — the write is permitted.
    assert proc.returncode == 0
    assert proc.stdout.decode("utf-8").strip() == "", (
        "fail-open violated: hook produced output when mailbox was unreachable: "
        + proc.stdout.decode("utf-8")
    )


def test_pre_tool_use_non_write_tool_no_output(tmp_home):
    client.ensure_running()
    proc = _run_hook("pre_tool_use.py", {
        "session_id": "sessC",
        "cwd": tmp_path_cwd(),
        "tool_name": "Read",
        "tool_input": {"file_path": os.path.join(tmp_path_cwd(), "x.py")},
    })
    assert proc.returncode == 0
    assert proc.stdout.decode("utf-8").strip() == ""


def test_post_tool_use_injects_inbox_then_read_receipt(tmp_home):
    client.ensure_running()
    cwd = os.getcwd()
    # Two sessions join the same repo board.
    a = client.request("join", {"session_id": "sessAAAA", "label": "alpha", "cwd": cwd})
    assert a["ok"] is True
    b = client.request("join", {"session_id": "sessBBBB", "label": "bravo", "cwd": cwd})
    assert b["ok"] is True
    # Session A broadcasts a note to everyone on the board.
    sent = client.request(
        "send",
        {
            "session_id": "sessAAAA",
            "to": "*",
            "kind": "note",
            "body": "deploying the auth refactor now",
        },
    )
    assert sent["ok"] is True

    # First run of post_tool_use as session B -> message injected.
    proc = _run_hook("post_tool_use.py", {"session_id": "sessBBBB"})
    rc = proc.returncode
    out = proc.stdout.decode("utf-8")
    assert rc == 0
    payload = json.loads(out)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "📬 Mailbox:" in ctx
    assert "[note] from alpha: deploying the auth refactor now" in ctx

    # Second run as session B -> nothing (read receipt already recorded).
    proc2 = _run_hook("post_tool_use.py", {"session_id": "sessBBBB"})
    assert proc2.returncode == 0
    assert proc2.stdout.decode("utf-8").strip() == ""


def test_user_prompt_submit_injects_inbox_then_read_receipt(tmp_home):
    client.ensure_running()
    cwd = os.getcwd()
    a = client.request("join", {"session_id": "sessCCCC", "label": "carol", "cwd": cwd})
    assert a["ok"] is True
    b = client.request("join", {"session_id": "sessDDDD", "label": "dave", "cwd": cwd})
    assert b["ok"] is True
    sent = client.request(
        "send",
        {
            "session_id": "sessCCCC",
            "to": "*",
            "kind": "handoff",
            "body": "the parser module is yours",
        },
    )
    assert sent["ok"] is True

    proc = _run_hook("user_prompt_submit.py", {"session_id": "sessDDDD"})
    assert proc.returncode == 0
    out = proc.stdout.decode("utf-8")
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert "📬 Mailbox:" in ctx
    assert "[handoff] from carol: the parser module is yours" in ctx

    proc2 = _run_hook("user_prompt_submit.py", {"session_id": "sessDDDD"})
    assert proc2.returncode == 0
    assert proc2.stdout.decode("utf-8").strip() == ""


def test_post_tool_use_fail_open_no_session_id(tmp_home):
    proc = _run_hook("post_tool_use.py", {"cwd": os.getcwd()})
    assert proc.returncode == 0
    assert proc.stdout.decode("utf-8").strip() == ""


def test_user_prompt_submit_fail_open_bad_stdin(tmp_home):
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC_DIR + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, os.path.join(HOOKS_DIR, "user_prompt_submit.py")],
        input=b"this is not json",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0
    assert proc.stdout.decode("utf-8").strip() == ""


def test_session_end_hook_releases_claims(tmp_home):
    from mailbox import client

    sid = "sess-end-1"
    cwd = REPO_ROOT

    # Bring up a real daemon on the temp socket and join + auto-claim a write.
    client.ensure_running()
    join_resp = client.request(
        "join",
        {"session_id": sid, "label": "ender", "cwd": cwd},
    )
    assert join_resp["ok"] is True

    target = os.path.join(cwd, "src", "mailbox", "engine.py")
    cw_resp = client.request(
        "check_write",
        {"session_id": sid, "abs_path": target},
    )
    assert cw_resp["ok"] is True
    assert cw_resp["data"]["decision"] == "allow"

    # Precondition: session is active and owns exactly one (auto) claim.
    who_before = client.request("whoami", {"session_id": sid})
    assert who_before["ok"] is True
    assert who_before["data"]["exists"] is True
    assert who_before["data"]["status"] == "active"

    mine_before = client.request(
        "list_claims",
        {"session_id": sid, "scope": "mine"},
    )
    assert mine_before["ok"] is True
    assert len(mine_before["data"]) == 1

    # Run the SessionEnd hook against the same live daemon.
    result = _run_hook(
        "session_end.py",
        {"session_id": sid, "cwd": cwd, "hook_event_name": "SessionEnd"},
    )
    assert result.returncode == 0

    # Postcondition: presence offline, no unreleased claims owned by the session.
    who_after = client.request("whoami", {"session_id": sid})
    assert who_after["ok"] is True
    assert who_after["data"]["status"] == "offline"

    mine_after = client.request(
        "list_claims",
        {"session_id": sid, "scope": "mine"},
    )
    assert mine_after["ok"] is True
    assert mine_after["data"] == []
