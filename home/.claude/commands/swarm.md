---
description: Fan out a substantive task across N federated Claude leads in iTerm2 tabs, coordinated via the mboard. /swarm <task> launches; /swarm close [<id>] reaps; /swarm status lists; /swarm sweep clears workdirs.
---

<<SWARM:$ARGUMENTS>>

You (the orchestrator) just received `/swarm <args>`. Pick the right action:

- **`<args>` is a task description** (or empty with a substantive pending
  task) → DECOMPOSE the task into 2-N parallel sub-tasks
  along its natural seams (component / layer / concern). For each sub-task pick
  a short lead name like "lead-1" and write a focused sub-task description.
  Then run:

  `python3 -m ccpkg.swarm launch --payload '{"task": "<one-line summary>", "subtasks": {"lead-1": "...", "lead-2": "..."}}'`

  The CLI mints a swarm_id, opens N iTerm2 tabs each running `claude
  --dangerously-skip-permissions`, and injects each lead's kickoff prompt. It
  prints the swarm_id on stdout.

  Then run `python3 -m ccpkg.swarm collect <swarm_id>` (via the helpers in
  `ccpkg/swarm/launch.py:collect`) to block until all leads signal done; read
  each `result.md`; synthesize one final answer for the user.

- **`<args>` starts with `close`** (e.g. `close`, `close abc12345`) → run
  `python3 -m ccpkg.swarm close [<id>]`. Closes one or all swarm tab sets.

- **`<args>` is `status`** → run `python3 -m ccpkg.swarm status`.

- **`<args>` is `sweep`** → run `python3 -m ccpkg.swarm sweep` (clears all
  workdirs under `/tmp/ccpkg-swarm/`).

Acknowledge in one line what you're doing, then execute. If `SWARM_LEAD` is
set in env, do NOT call `/swarm` (no nested swarms — refuse and explain).
