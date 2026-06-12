"""Swarm kickoff prompt + inbox.md body templates.

The kickoff is a SINGLE LINE injected into the lead's REPL: iTerm's `write text`
submits on every embedded newline, so a multi-line kickoff would fire partial
prompts (Probe 2 finding). All real instruction lives in inbox.md, which the
lead reads. The lead invokes the mboard CLI by its absolute path
(`~/.claude/mboard/mboard`) because `mboard` is not on $PATH, and `send`
routes to the session's primary board implicitly (there is no --board flag).
"""

# Absolute path to the mboard CLI — `mboard` is not on $PATH anywhere; the only
# entry point is this symlink (-> opt-prefixed homebrew libexec).
MBOARD = "~/.claude/mboard/mboard"

KICKOFF_TEMPLATE = (
    "You are swarm lead {lead} on swarm {swarm_id}. Read {inbox_path} now and "
    "follow it exactly — it has your sub-task, coordination rules, and the "
    "done-signal to run when finished, and do NOT call /swarm (no nested swarms)."
)


def kickoff(swarm_id, lead, inbox_path):
    """One-line REPL kickoff pointing the lead at its inbox.md (no newlines)."""
    return KICKOFF_TEMPLATE.format(
        lead=lead, swarm_id=swarm_id, inbox_path=inbox_path)


INBOX_TEMPLATE = """\
---
swarm_id: {swarm_id}
lead: {lead}
sibling_leads: {siblings}
main_task: {task}
---

## Mission context

You are **lead {lead}** on swarm {swarm_id}. The overall swarm task is:

  {task}

The sub-task below is YOUR slice of that. Your sibling leads ({siblings}) own the
other slices in parallel — stay inside your slice and coordinate at the seams.

## Your sub-task

{subtask}

## Build your own team — do NOT run this solo

You are a TEAM LEAD, not a worker. Stand up your OWN native agent team to execute
this sub-task — the same persistent agent-team protocol the orchestrator used to
launch you:

1. Decompose your sub-task along its natural seams.
2. `TeamCreate` a team, then spawn one focused teammate per seam with the `Agent`
   tool (`run_in_background`), and coordinate them via the mboard.
3. Synthesize their outputs into your result.

Only skip the team and do the work yourself if the sub-task is genuinely atomic
(one small change with no parallelizable structure) — and say so in your result.

Recursion ban: do NOT call /swarm — no nested swarms (your tier is agent teams,
not swarms).

## Coordination

You share the repo board with the orchestrator and your sibling leads. Use
`{mboard} send` / `{mboard} inbox` to coordinate (the bare `mboard` command is
not on PATH — always use that absolute path). File claims are auto-enforced via
the mboard PreToolUse hook, so avoid clobbering siblings.

## Done signal

When you finish, write your result to $SWARM_WORKDIR/result.md and run:

  {mboard} send --kind swarm_done \\
    '{{"lead": "{lead}", "status": "ok", "result_path": "'$SWARM_WORKDIR'/result.md"}}'

(`send` posts to your primary board swarm-{swarm_id} automatically — it takes no
per-message board argument.) Then exit the session.
"""


def inbox_body(swarm_id, lead, sibling_leads, subtask, task):
    siblings = "[" + ", ".join(sibling_leads) + "]" if sibling_leads else "[]"
    return INBOX_TEMPLATE.format(
        swarm_id=swarm_id,
        lead=lead,
        siblings=siblings,
        subtask=subtask,
        task=task,
        mboard=MBOARD,
    )
