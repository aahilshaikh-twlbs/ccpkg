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


def settings_file(config_dir):
    # nuke writes ultracode into the user-level settings.json (the only file the
    # harness reads for the ultracode setting).
    return Path(config_dir) / "settings.json"


def read_settings(config_dir):
    p = settings_file(config_dir)
    return json.loads(p.read_text()) if p.exists() else {}


def ups(prompt):
    return {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": prompt}


# ---- arming -------------------------------------------------------------

def test_arm_via_slash_sets_ultracode_true(tmp_path):
    proc = run_hook(ups("/nuke"), tmp_path)
    assert proc.returncode == 0
    assert read_settings(tmp_path).get("ultracode") is True
    assert "NUKE MODE ARMED" in injected(proc)


def test_arm_via_arm_alias(tmp_path):
    run_hook(ups("/nuke arm"), tmp_path)
    assert read_settings(tmp_path).get("ultracode") is True


def test_arm_via_sentinel(tmp_path):
    # The command body expands to <<NUKE:$ARGUMENTS>>; bare /nuke -> empty arg.
    proc = run_hook(ups("kick off <<NUKE:>>"), tmp_path)
    assert read_settings(tmp_path).get("ultracode") is True
    assert "ARMED" in injected(proc)


def test_arm_preserves_existing_settings_keys(tmp_path):
    settings_file(tmp_path).write_text(json.dumps({"awsProfile": "prod"}))
    run_hook(ups("/nuke"), tmp_path)
    data = read_settings(tmp_path)
    assert data["ultracode"] is True
    assert data["awsProfile"] == "prod"  # untouched


# ---- disarming ----------------------------------------------------------

def test_disarm_via_off_removes_ultracode(tmp_path):
    settings_file(tmp_path).write_text(json.dumps({"ultracode": True, "awsProfile": "prod"}))
    proc = run_hook(ups("/nuke off"), tmp_path)
    data = read_settings(tmp_path)
    assert "ultracode" not in data
    assert data["awsProfile"] == "prod"  # other keys preserved
    assert "DISARMED" in injected(proc)


def test_disarm_via_disarm_alias(tmp_path):
    settings_file(tmp_path).write_text(json.dumps({"ultracode": True}))
    run_hook(ups("/nuke disarm"), tmp_path)
    assert "ultracode" not in read_settings(tmp_path)


def test_disarm_via_sentinel_off(tmp_path):
    settings_file(tmp_path).write_text(json.dumps({"ultracode": True}))
    run_hook(ups("<<NUKE:off>>"), tmp_path)
    assert "ultracode" not in read_settings(tmp_path)


def test_off_takes_precedence_over_nuke_substring(tmp_path):
    # "/nuke off" contains "/nuke" — must be read as disarm, not arm.
    settings_file(tmp_path).write_text(json.dumps({"ultracode": True}))
    run_hook(ups("/nuke off"), tmp_path)
    assert "ultracode" not in read_settings(tmp_path)


# ---- standing directive while armed ------------------------------------

def test_standing_directive_when_armed_no_intent(tmp_path):
    settings_file(tmp_path).write_text(json.dumps({"ultracode": True}))
    proc = run_hook(ups("now do the real work"), tmp_path)
    text = injected(proc)
    assert "NUKE MODE active" in text
    assert "agent teams" in text


def test_silent_when_not_armed_no_intent(tmp_path):
    proc = run_hook(ups("just a normal prompt"), tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


# ---- fail-open ----------------------------------------------------------

def test_fail_open_empty_stdin(tmp_path):
    proc = run_hook(None, tmp_path, raw="")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_fail_open_malformed_json(tmp_path):
    proc = run_hook(None, tmp_path, raw="{not valid")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_arm_without_session_id_still_works(tmp_path):
    # State is global (settings), not per-session — no session_id needed.
    proc = run_hook({"hook_event_name": "UserPromptSubmit", "prompt": "/nuke"}, tmp_path)
    assert proc.returncode == 0
    assert read_settings(tmp_path).get("ultracode") is True


# ---- v3: bundle bypassPermissions + sidecar -----------------------------

def sidecar(config_dir):
    return Path(config_dir) / "nuke" / "prior.json"


def read_sidecar(config_dir):
    p = sidecar(config_dir)
    return json.loads(p.read_text()) if p.exists() else None


def write_settings(config_dir, data):
    settings_file(config_dir).write_text(json.dumps(data))


# ---- arm: bundle bypassPermissions ----

def test_arm_sets_bypass_permissions_and_records_no_prior(tmp_path):
    run_hook(ups("/nuke"), tmp_path)
    data = read_settings(tmp_path)
    assert data["ultracode"] is True
    assert data["permissions"]["defaultMode"] == "bypassPermissions"
    # No prior defaultMode existed -> sidecar records null.
    assert read_sidecar(tmp_path) == {"defaultMode": None}


def test_arm_records_prior_default_mode(tmp_path):
    write_settings(tmp_path, {"permissions": {"defaultMode": "auto"}})
    run_hook(ups("/nuke"), tmp_path)
    data = read_settings(tmp_path)
    assert data["permissions"]["defaultMode"] == "bypassPermissions"
    assert read_sidecar(tmp_path) == {"defaultMode": "auto"}


def test_arm_preserves_other_permissions_keys(tmp_path):
    write_settings(tmp_path, {"permissions": {"defaultMode": "auto",
                                              "allow": ["Bash(ls)"]}})
    run_hook(ups("/nuke"), tmp_path)
    data = read_settings(tmp_path)
    assert data["permissions"]["defaultMode"] == "bypassPermissions"
    assert data["permissions"]["allow"] == ["Bash(ls)"]  # untouched


def test_rearm_is_idempotent_and_preserves_original_prior(tmp_path):
    write_settings(tmp_path, {"permissions": {"defaultMode": "auto"}})
    run_hook(ups("/nuke"), tmp_path)
    # Second arm must NOT overwrite the sidecar with "bypassPermissions".
    run_hook(ups("/nuke"), tmp_path)
    assert read_sidecar(tmp_path) == {"defaultMode": "auto"}


# ---- disarm: restore prior defaultMode ----

def test_disarm_restores_prior_default_mode(tmp_path):
    write_settings(tmp_path, {"permissions": {"defaultMode": "auto"}})
    run_hook(ups("/nuke"), tmp_path)
    run_hook(ups("/nuke off"), tmp_path)
    data = read_settings(tmp_path)
    assert "ultracode" not in data
    assert data["permissions"]["defaultMode"] == "auto"
    assert read_sidecar(tmp_path) is None  # cleared


def test_disarm_deletes_default_mode_when_no_prior(tmp_path):
    # No prior permissions block at all.
    run_hook(ups("/nuke"), tmp_path)
    run_hook(ups("/nuke off"), tmp_path)
    data = read_settings(tmp_path)
    assert "ultracode" not in data
    # permissions.defaultMode must not linger (it was never there).
    assert "permissions" not in data or "defaultMode" not in data["permissions"]
    assert read_sidecar(tmp_path) is None


def test_disarm_without_sidecar_leaves_default_mode_alone(tmp_path):
    # Simulate the user manually setting "ultracode" without arming via the hook.
    write_settings(tmp_path, {"ultracode": True,
                              "permissions": {"defaultMode": "acceptEdits"}})
    run_hook(ups("/nuke off"), tmp_path)
    data = read_settings(tmp_path)
    assert "ultracode" not in data
    # No sidecar -> hook should not touch defaultMode.
    assert data["permissions"]["defaultMode"] == "acceptEdits"


def test_disarm_preserves_other_permissions_keys(tmp_path):
    write_settings(tmp_path, {"permissions": {"defaultMode": "auto",
                                              "allow": ["Bash(ls)"]}})
    run_hook(ups("/nuke"), tmp_path)
    run_hook(ups("/nuke off"), tmp_path)
    data = read_settings(tmp_path)
    assert data["permissions"]["defaultMode"] == "auto"
    assert data["permissions"]["allow"] == ["Bash(ls)"]
