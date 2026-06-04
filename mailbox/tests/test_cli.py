import os

import pytest

from mailbox import cli, client


def test_main_no_session_errors(tmp_home, monkeypatch, capsys):
    monkeypatch.delenv("MAILBOX_SESSION_ID", raising=False)
    rc = cli.main(["whoami"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "no session id" in captured.err


def test_join_whoami_claims_roundtrip(tmp_home, capsys):
    client.ensure_running()
    sid = "sess-cli-1"

    rc = cli.main(["--session", sid, "join", "--label", "tester"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "tester" in out

    rc = cli.main(["--session", sid, "whoami"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "tester" in out
    assert "'exists': True" in out

    rc = cli.main(["--session", sid, "claims"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "(no claims)" in out


def test_claim_abspaths_and_lists(tmp_home, capsys):
    client.ensure_running()
    sid = "sess-cli-2"

    rc = cli.main(["--session", sid, "join", "--label", "claimer"])
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["--session", sid, "claim", "src/foo.py", "--note", "mine"])
    assert rc == 0
    capsys.readouterr()

    rc = cli.main(["--session", sid, "claims", "--mine"])
    out = capsys.readouterr().out
    assert rc == 0
    expected = os.path.abspath("src/foo.py")
    assert expected in out
    assert "mine" in out


def test_ok_false_exits_1_and_prints_error(tmp_home, monkeypatch, capsys):
    def fake_request(op, args=None, session=None, autospawn=True):
        return {"ok": False, "error": "boom: nope"}

    monkeypatch.setattr(client, "request", fake_request)
    rc = cli.main(["--session", "sX", "whoami"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "boom: nope" in captured.err


import subprocess


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _shim_env(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        os.path.join(_REPO_ROOT, "src")
        + os.pathsep
        + env.get("PYTHONPATH", "")
    )
    env["MAILBOX_HOME"] = str(tmp_path / "home")
    env["MAILBOX_SOCKET"] = str(tmp_path / "mailboxd.sock")
    return env


def test_bin_mailbox_shim_help_exits_zero(tmp_path):
    shim = os.path.join(_REPO_ROOT, "bin", "mailbox")
    assert os.path.exists(shim), "bin/mailbox shim is missing"
    assert os.access(shim, os.X_OK), "bin/mailbox is not executable"

    result = subprocess.run(
        [shim, "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_shim_env(tmp_path),
        timeout=30,
    )

    out = result.stdout.decode("utf-8", "replace")
    err = result.stderr.decode("utf-8", "replace")
    assert result.returncode == 0, (
        "exit %d\nstdout=%s\nstderr=%s" % (result.returncode, out, err)
    )
    # argparse --help always prints a "usage:" line. Assert only on this
    # guaranteed marker (combined stream); do NOT assume the literal word
    # "mailbox" appears, because `python -m mailbox.cli` gives argparse the
    # default prog "__main__.py" unless Task 14 sets prog="mailbox".
    assert "usage" in (out + err).lower(), (
        "no argparse usage in output\nstdout=%s\nstderr=%s" % (out, err)
    )


def test_bin_mailbox_shim_runs_from_any_cwd(tmp_path):
    # The shim must resolve its own dir -> ../src, not depend on caller cwd.
    shim = os.path.join(_REPO_ROOT, "bin", "mailbox")
    assert os.path.exists(shim), "bin/mailbox shim is missing"

    workdir = tmp_path / "elsewhere"
    workdir.mkdir()

    result = subprocess.run(
        [shim, "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_shim_env(tmp_path),
        cwd=str(workdir),
        timeout=30,
    )
    out = result.stdout.decode("utf-8", "replace")
    err = result.stderr.decode("utf-8", "replace")
    assert result.returncode == 0, (
        "exit %d\nstdout=%s\nstderr=%s" % (result.returncode, out, err)
    )
    assert "usage" in (out + err).lower(), (
        "no argparse usage in output\nstdout=%s\nstderr=%s" % (out, err)
    )
