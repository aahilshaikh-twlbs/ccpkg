"""Swarm orchestrator: mint id, prep, spawn, inject, wait, synthesize."""
import os
import shlex

from . import iterm, lifecycle, prompts, workdir


class NestedSwarmError(RuntimeError):
    pass


def _print_assisted(swarm_id, lead, env, cmd, kickoff_text):
    print("=" * 60)
    print(f"# B-assisted lead: {lead}")
    print("# Open a new terminal tab in this repo and run:")
    exports = " ".join("{}={}".format(k, shlex.quote(str(v)))
                       for k, v in env.items())
    print(f"  {exports} {cmd}")
    print("# Then paste this as your first prompt to that claude session:")
    print()
    print(kickoff_text)
    print("=" * 60)


def launch_swarm(task, subtasks, fallback="assisted",
                 presence_timeout=45.0, total_timeout=600.0):
    """Launch a swarm.

    task:     human-readable task description (for meta.json).
    subtasks: dict {lead_name: subtask_text}.
    fallback: "assisted" (recommended) or "raise" — what to do if osascript fails.
    """
    if os.environ.get("SWARM_LEAD"):
        raise NestedSwarmError("refusing to launch a nested swarm "
                               "(SWARM_LEAD is set in env)")

    swarm_id = workdir.mint_swarm_id()
    leads = list(subtasks.keys())
    inboxes = {
        lead: prompts.inbox_body(
            swarm_id=swarm_id,
            lead=lead,
            sibling_leads=[l for l in leads if l != lead],
            subtask=subtasks[lead],
            task=task,
        )
        for lead in leads
    }
    workdir.setup(swarm_id, leads, task, inboxes)

    swarm_board = "swarm-" + swarm_id
    pane_ids = {}
    fallback_used = False
    # Leads must launch in the orchestrator's repo: a new iTerm tab inherits the
    # active session's cwd, not ours (Probe 2 finding).
    repo_cwd = os.getcwd()

    for lead in leads:
        env = {
            "MBOARD_LABEL": f"swarm-{swarm_id}-{lead}",
            "MBOARD_BOARD": swarm_board,
            "SWARM_ID": swarm_id,
            "SWARM_LEAD": lead,
            "SWARM_WORKDIR": workdir.lead_dir(swarm_id, lead),
        }
        cmd = "claude --dangerously-skip-permissions"
        kickoff = prompts.kickoff(swarm_id, lead,
                                  workdir.inbox_path(swarm_id, lead))
        try:
            pid = iterm.spawn_tab(env, cmd, cwd=repo_cwd)
            pane_ids[lead] = pid
        except iterm.ITermError as exc:
            if fallback != "assisted":
                raise
            fallback_used = True
            _print_assisted(swarm_id, lead, env, cmd, kickoff)
            continue

        # Wait for presence on the swarm board, then inject kickoff.
        if lifecycle.wait_for_presence(swarm_id, lead, timeout=presence_timeout):
            try:
                iterm.inject(pid, kickoff)
            except iterm.ITermError:
                fallback_used = True
                _print_assisted(swarm_id, lead, env, cmd, kickoff)
        else:
            fallback_used = True
            _print_assisted(swarm_id, lead, env, cmd, kickoff)

    workdir.record_pane_ids(swarm_id, pane_ids)
    return swarm_id


def collect(swarm_id, total_timeout=600.0):
    """Block until all leads done / timeout; return {lead: {status, result_text}}."""
    from .workdir import list_swarms, result_path
    meta = next((m for m in list_swarms() if m["swarm_id"] == swarm_id), None)
    if not meta:
        return {}
    leads = meta["leads"]
    raw = lifecycle.wait_for_all(swarm_id, leads, timeout=total_timeout)
    out = {}
    for lead, info in raw.items():
        result_text = None
        rp = info.get("result_path") or result_path(swarm_id, lead)
        try:
            with open(rp) as fh:
                result_text = fh.read()
        except OSError:
            pass
        out[lead] = {"status": info["status"], "result_text": result_text}
    return out
