import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "home" / ".claude" / "hooks" / "nuke.py"


def run_hook(payload, config_dir, raw=None):
    """Invoke nuke.py as Claude Code would: JSON on stdin, CLAUDE_CONFIG_DIR set."""
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(config_dir))
    data = raw if raw is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=data,
        capture_output=True,
        text=True,
        env=env,
    )


def injected(proc):
    """Return the additionalContext string, or '' if the hook emitted nothing."""
    if not proc.stdout.strip():
        return ""
    return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]


def flag_for(config_dir, session_id):
    return Path(config_dir) / "nuke" / (session_id + ".flag")


def test_arm_via_sentinel_creates_flag_and_injects(tmp_path):
    proc = run_hook(
        {"hook_event_name": "UserPromptSubmit", "session_id": "abc",
         "prompt": "kick things off <<NUKE-ARM>>"},
        tmp_path,
    )
    assert proc.returncode == 0
    assert flag_for(tmp_path, "abc").exists()
    assert "NUKE MODE ACTIVE" in injected(proc)


def test_arm_via_slash_command_token(tmp_path):
    proc = run_hook(
        {"hook_event_name": "UserPromptSubmit", "session_id": "abc",
         "prompt": "/nuke"},
        tmp_path,
    )
    assert flag_for(tmp_path, "abc").exists()
    assert "NUKE MODE ACTIVE" in injected(proc)


def test_sticky_injects_without_sentinel_when_flag_present(tmp_path):
    (tmp_path / "nuke").mkdir()
    flag_for(tmp_path, "abc").write_text("on")
    proc = run_hook(
        {"hook_event_name": "UserPromptSubmit", "session_id": "abc",
         "prompt": "now do the actual work"},
        tmp_path,
    )
    assert "NUKE MODE ACTIVE" in injected(proc)


def test_disarmed_by_default_no_output(tmp_path):
    proc = run_hook(
        {"hook_event_name": "UserPromptSubmit", "session_id": "abc",
         "prompt": "just a normal prompt"},
        tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_session_isolation(tmp_path):
    (tmp_path / "nuke").mkdir()
    flag_for(tmp_path, "abc").write_text("on")  # armed session
    proc = run_hook(
        {"hook_event_name": "UserPromptSubmit", "session_id": "xyz",
         "prompt": "different session"},
        tmp_path,
    )
    assert proc.stdout.strip() == ""  # xyz is not armed


def test_fail_open_empty_stdin(tmp_path):
    proc = run_hook(None, tmp_path, raw="")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_fail_open_malformed_json(tmp_path):
    proc = run_hook(None, tmp_path, raw="{not valid")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_no_session_id_does_nothing(tmp_path):
    proc = run_hook(
        {"hook_event_name": "UserPromptSubmit", "prompt": "<<NUKE-ARM>>"},
        tmp_path,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    assert not (tmp_path / "nuke").exists()


def test_session_end_clears_flag(tmp_path):
    (tmp_path / "nuke").mkdir()
    flag_for(tmp_path, "abc").write_text("on")
    proc = run_hook(
        {"hook_event_name": "SessionEnd", "session_id": "abc"},
        tmp_path,
    )
    assert proc.returncode == 0
    assert not flag_for(tmp_path, "abc").exists()


def test_session_end_missing_flag_is_noop(tmp_path):
    proc = run_hook(
        {"hook_event_name": "SessionEnd", "session_id": "never-armed"},
        tmp_path,
    )
    assert proc.returncode == 0


def test_session_end_does_not_inject(tmp_path):
    (tmp_path / "nuke").mkdir()
    flag_for(tmp_path, "abc").write_text("on")
    proc = run_hook(
        {"hook_event_name": "SessionEnd", "session_id": "abc"},
        tmp_path,
    )
    assert proc.stdout.strip() == ""


def test_command_file_carries_sentinel_and_description():
    cmd = Path(__file__).resolve().parents[1] / "home" / ".claude" / "commands" / "nuke.md"
    text = cmd.read_text()
    # Frontmatter description so it shows in the command list.
    assert text.startswith("---")
    assert "description:" in text.split("---", 2)[1]
    # The sentinel the hook arms on must be present in the expansion.
    assert "<<NUKE-ARM>>" in text
