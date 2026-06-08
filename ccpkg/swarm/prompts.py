"""Swarm kickoff prompt + inbox.md body templates."""

KICKOFF_TEMPLATE = """\
You are swarm lead {lead} on swarm {swarm_id}. Your sub-task is in
$SWARM_WORKDIR/inbox.md — read it now and follow it exactly.

Coordination: you share the mailbox repo board with the orchestrator and your
sibling leads ({siblings}). Use `mailbox send` / `mailbox inbox` to coordinate.
File claims are auto-enforced (mailbox PreToolUse hook).

If your sub-task benefits from parallel sub-agents, spawn your OWN team via the
standard agent-team protocol (TeamCreate + Agent).

CRITICAL: do NOT call /swarm yourself. No nested swarms.

When you finish, write your result to $SWARM_WORKDIR/result.md and run:
  mailbox send --board {swarm_board} --kind swarm_done \\
    '{{"lead": "{lead}", "status": "ok", "result_path": "'$SWARM_WORKDIR'/result.md"}}'

Then stop (the orchestrator collects from there).
"""


def kickoff(swarm_id, lead, sibling_leads, swarm_board):
    siblings = ", ".join(sibling_leads) if sibling_leads else "none"
    return KICKOFF_TEMPLATE.format(
        lead=lead,
        swarm_id=swarm_id,
        siblings=siblings,
        swarm_board=swarm_board,
    )


INBOX_TEMPLATE = """\
---
swarm_id: {swarm_id}
lead: {lead}
sibling_leads: {siblings}
---

## Your sub-task

{subtask}

## Coordination

You share the repo board with the orchestrator and your sibling leads. Use
`mailbox send` / `mailbox inbox` to coordinate. Use file claims (auto via
mailbox PreToolUse) to avoid clobbering siblings.

## Done signal

When you finish, write your result to $SWARM_WORKDIR/result.md and:

  mailbox send --board swarm-{swarm_id} --kind swarm_done \\
    '{{"lead": "{lead}", "status": "ok", "result_path": "'$SWARM_WORKDIR'/result.md"}}'

Then exit the session.
"""


def inbox_body(swarm_id, lead, sibling_leads, subtask):
    siblings = "[" + ", ".join(sibling_leads) + "]" if sibling_leads else "[]"
    return INBOX_TEMPLATE.format(
        swarm_id=swarm_id,
        lead=lead,
        siblings=siblings,
        subtask=subtask,
    )
