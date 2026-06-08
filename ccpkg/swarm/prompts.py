"""Swarm kickoff prompt + inbox.md body templates.

The kickoff is a SINGLE LINE injected into the lead's REPL: iTerm's `write text`
submits on every embedded newline, so a multi-line kickoff would fire partial
prompts (Probe 2 finding). All real instruction lives in inbox.md, which the
lead reads. The lead invokes the mailbox CLI by its absolute path
(`~/.claude/mailbox/mailbox`) because `mailbox` is not on $PATH, and `send`
routes to the session's primary board implicitly (there is no --board flag).
"""

# Absolute path to the mailbox CLI — `mailbox` is not on $PATH anywhere; the only
# entry point is this symlink (-> opt-prefixed homebrew libexec).
MAILBOX = "~/.claude/mailbox/mailbox"

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
---

## Your sub-task

{subtask}

## Coordination

You share the repo board with the orchestrator and your sibling leads. Use
`{mailbox} send` / `{mailbox} inbox` to coordinate (the bare `mailbox` command is
not on PATH — always use that absolute path). File claims are auto-enforced via
the mailbox PreToolUse hook, so avoid clobbering siblings.

## Done signal

When you finish, write your result to $SWARM_WORKDIR/result.md and run:

  {mailbox} send --kind swarm_done \\
    '{{"lead": "{lead}", "status": "ok", "result_path": "'$SWARM_WORKDIR'/result.md"}}'

(`send` posts to your primary board swarm-{swarm_id} automatically — it takes no
per-message board argument.) Then exit the session.
"""


def inbox_body(swarm_id, lead, sibling_leads, subtask):
    siblings = "[" + ", ".join(sibling_leads) + "]" if sibling_leads else "[]"
    return INBOX_TEMPLATE.format(
        swarm_id=swarm_id,
        lead=lead,
        siblings=siblings,
        subtask=subtask,
        mailbox=MAILBOX,
    )
