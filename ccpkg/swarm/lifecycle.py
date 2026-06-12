"""Mboard polling for swarm lifecycle: lead presence + done collection."""
import json
import os
import sys
import time


def _mboard_client():
    """Return the vendored mboard client (imported lazily so tests can patch)."""
    src = os.path.expanduser("~/.claude/mboard/src")
    if os.path.isdir(src) and src not in sys.path:
        sys.path.insert(0, src)
    # Also try the repo's vendored copy when running from the repo.
    repo_src = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "mboard", "src")
    if os.path.isdir(repo_src) and repo_src not in sys.path:
        sys.path.insert(0, repo_src)
    from mboard import client
    return client


def _board(swarm_id):
    return "swarm-" + swarm_id


def _orchestrator_session_id(swarm_id):
    return "swarm-" + swarm_id + "-orchestrator"


def _ensure_orchestrator(client, swarm_id):
    """Idempotently join an orchestrator presence to the swarm board and return
    its session_id.

    The daemon's ps/poll_inbox derive the board set from the *caller's* own
    presence (mboard/src/mboard/protocol.py strips any `board` kwarg), so the
    orchestrator must be a real session joined to the swarm board to see the
    leads. Re-joining is cheap and also refreshes the orchestrator's heartbeat
    so its presence does not go stale during a long collect.
    """
    sid = _orchestrator_session_id(swarm_id)
    client.request("join", {
        "session_id": sid,
        "label": sid,
        "cwd": os.getcwd(),
        "board_name": _board(swarm_id),
    })
    return sid


def wait_for_presence(swarm_id, lead, timeout=45.0, poll_interval=1.0):
    """Return True once the lead's mboard presence is active, else False on timeout."""
    target_label = "swarm-" + swarm_id + "-" + lead
    deadline = time.monotonic() + timeout
    client = _mboard_client()
    sid = _ensure_orchestrator(client, swarm_id)
    while time.monotonic() < deadline:
        resp = client.request("ps", {"session_id": sid})
        if resp.get("ok"):
            for p in resp.get("data", []) or []:
                if (p.get("label") == target_label
                        and p.get("status") == "active"):
                    return True
        time.sleep(poll_interval)
    return False


def poll_done(swarm_id):
    """Return all swarm_done messages currently visible to the orchestrator.

    Each is a dict with: lead, status, result_path (decoded from body JSON).
    """
    client = _mboard_client()
    sid = _ensure_orchestrator(client, swarm_id)
    resp = client.request("poll_inbox", {"session_id": sid})
    if not resp.get("ok"):
        return []
    out = []
    for m in resp.get("data", []) or []:
        if m.get("kind") != "swarm_done":
            continue
        try:
            parsed = json.loads(m.get("body") or "{}")
        except ValueError:
            continue
        out.append(parsed)
    return out


def wait_for_all(swarm_id, leads, timeout=600.0, poll_interval=2.0):
    """Block until every lead has a swarm_done or timeout.

    Returns {lead: {status, result_path}} where status="timeout" for any
    lead that never signaled.
    """
    deadline = time.monotonic() + timeout
    results = {}
    leads_set = set(leads)
    while time.monotonic() < deadline and len(results) < len(leads_set):
        for d in poll_done(swarm_id):
            if d.get("lead") in leads_set and d["lead"] not in results:
                results[d["lead"]] = {
                    "status": d.get("status", "ok"),
                    "result_path": d.get("result_path"),
                }
        if len(results) >= len(leads_set):
            break
        time.sleep(poll_interval)
    for lead in leads_set - set(results):
        results[lead] = {"status": "timeout", "result_path": None}
    return results
