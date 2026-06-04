# Mailbox — ambient cross-session coordination for Claude Code

**Date:** 2026-06-03
**Status:** Approved design, pre-implementation

## Problem

Multiple Claude Code sessions and agent-team members work in the same repos at the
same time with **no shared awareness of each other**. Native agent teams have
`SendMessage`/`Task*` for coordination *inside a single team*, but independent
sessions (e.g. five separate `/handoff` processes) are completely blind to one
another. The result is overlapping edits that overwrite each other's work or, worse,
leave the active codebase in a corrupt half-edited state.

We want sessions to **work in tandem without overlap**: hand off one task to N
sessions (or one agent team), have each take a different part, stay out of each
other's files, and sync only when there's a real dependency or a need to cooperate.

## Design principles

1. **Ambient and never summoned.** This is the most important property. There is no
   keyword, skill, or slash command to "start" collaborating. Pure hooks make it the
   default state: every session auto-joins on start, heartbeats and checks mail on
   every tool call, and the daemon proactively tells co-located sessions about each
   other. If two sessions are in the same repo/dir, they are *already* collaborating.
2. **Communication-first, with a hard anti-collision guarantee underneath.** The
   point is coordination; claims are the mechanism that makes collaboration safe.
3. **One unified substrate.** Independent sessions and in-team members use the exact
   same mechanism (the `mailbox` CLI over a socket), so there's no split-brain
   between "in-team" and "cross-session" coordination.
4. **Fail-open.** A buggy or down mailbox must never wedge real work. The only thing
   that ever blocks a write is a deliberate live-conflict denial.

## Architecture

A long-lived **`mailboxd` daemon owns all state** and is the single writer, so there
are no file-write races by construction. Hooks and the `mailbox` CLI are thin clients
that talk to it over a **Unix domain socket** (newline-delimited JSON request/reply).

```
~/.claude/mailbox/              # runtime + install location
  mailboxd.py                   # the daemon: owns state, serves socket, runs timers
  mailbox                       # thin CLI client (shell shim → socket)
  mailboxd.sock                 # Unix domain socket
  mailboxd.pid                  # single-instance guard
  mailboxd.log
  state/                        # persistence — human-readable, cat-able for debugging
    boards/<board-id>/
      meta.json                 # name, origin (repo path | named), created
      presence/<session-id>.json
      claims/<claim-id>.json
      messages/<msg-id>.json
```

- **Source/dev repo:** `~/Documents/Code/mailbox` (git-tracked: code, tests, docs).
  Deployed/symlinked into `~/.claude/mailbox` for runtime.
- **Daemon-owned state still lives as on-disk JSON** so the substrate stays
  transparent (`cat` any claim to debug) and the daemon recovers cleanly on restart
  by reloading `state/`. All *writes* go through the socket; atomic temp+rename on
  every write for crash safety. This is separate from the existing
  `~/.claude/daemon` (the notify daemon) — own socket, pidfile, log.
- **Language:** Python core (clean JSON + glob + atomic writes + testable), thin
  `mailbox` shell shim, Python invoked directly from hooks.

### Lifecycle

- `SessionStart` hook connects to the socket; if dead, it **auto-spawns the daemon**
  (pidfile-guarded, like ssh-agent). If spawn fails, hooks fail-open.
- Daemon runs **server-side timers**: heartbeat-timeout flips a session stale and
  downgrades its claims to warn; TTL expiry reaps `auto` claims; periodic GC removes
  offline presence and read messages. No client polls for liveness — the daemon knows.

## Data model

Three record types, mutated **only by the daemon** (so heartbeat/`read_by` updates are
race-free).

**Presence** — `session_id`, human `label`, `team`/`member` (if in an agent team),
`cwd`, `joined`, `last_heartbeat`, `status` (`active`|`offline`). Liveness = heartbeat
fresh within a threshold (default 90s).

**Claim** — `id`, `session_id` + `label`, **`paths`** (list of globs, stored
**absolute** so cross-repo boards are unambiguous), `kind` (`auto`|`explicit`),
optional `note`, `created`, `expires` (auto = short TTL refreshed by heartbeat;
explicit = long), `released` (bool).

**Message** — `id`, `from` (session+label), `to` (a session/label, or `*` broadcast),
`kind` (`note`|`release-request`|`dep-signal`|`handoff`|`done`), `body`, optional
`ref_paths`, `created`, `read_by[]`.

## Boards (what binds sessions together)

A session can sit on **multiple boards at once**.

- **Auto repo board (zero effort):** `SessionStart` derives the board from the
  **working-tree root** (`git rev-parse --show-toplevel`) → `repo-<hash>`, or falls
  back to `cwd-<hash>` if not in a repo. Every session lands here automatically and
  immediately sees siblings in the same checkout.
  - **Worktrees are intentionally separate boards.** Using the working-tree root (not
    the shared `--git-common-dir`) means two sessions in *different* worktrees of the
    same repo get *different* boards — correct, because worktrees check out different
    files and can't collide. Only sessions in the **same checkout** share a board and
    need anti-collision. This matches the heavy-worktree workflow.
- **Named boards (cross-project / isolated efforts):** `join` also reads
  `MAILBOX_BOARD=<slug>` from the env; if set, the session *additionally* joins that
  named board. This is the hook for cross-repo work and isolated sub-efforts.
- **Identity/label:** defaults to team `member` name, else a generated slug (e.g.
  `bcctui-polish`); overridable via `--label` or `MAILBOX_LABEL`.

## Enforcement flow (anti-collision guarantee)

Chokepoint: a `PreToolUse` hook matching `Edit|Write|MultiEdit|NotebookEdit`. Before
any mutation:

1. Hook sends the daemon `{session_id, abs_path}`.
2. Daemon scans claims (across the session's boards) whose globs match `abs_path`,
   owned by a **different** session, not released.
3. For each conflict, daemon checks the holder's liveness (it already tracks
   heartbeats):
   - **Holder live** → reply `deny`. Hook blocks the tool, reporting who holds it
     (`label`), their `note`, how long ago they were active, and the coordination
     one-liner (`mailbox request-release <path>`).
   - **Holder stale** → reply `warn`. Hook allows but injects a loud warning + "run
     `mailbox seize <path>` to take it over."
4. **No conflict** → daemon records an `auto` claim for this session (refreshed by
   heartbeat) and replies `allow`.

**Fail-open:** if the daemon is unreachable or errors internally, the hook **allows**
the write. Escape hatches: `mailbox release --force <id>`, `mailbox seize <path>`.

The auto-claim layer is the un-forgettable safety net (can't be skipped). Explicit
claims (`mailbox claim`) handle "hands off, big refactor incoming" by staking
territory before any file is touched.

## Messaging & delivery

- **Send:** `mailbox send --to <label|*> [--kind] "body"` → daemon stores + routes.
- **Delivery:** the `PostToolUse`/`UserPromptSubmit` hooks already ping the daemon for
  heartbeat — the same call returns **pending messages** for this session (broadcasts
  on joined boards + directed). The hook injects them as `additionalContext`; the
  daemon marks `read_by`. So an agent "checks mail" every turn/tool call with zero
  discipline. (Daemon-push to idle sessions is a later optimization; turn-boundary
  pull is v1.)
- **Proactive co-location notice:** when the daemon sees a second session join a board
  that already has a live member, it queues a broadcast `note` so each side learns
  "you're not alone in this repo" on their next tick — collaboration starts on its
  own, unprompted.
- **Coordination verbs are message `kind`s:** `release-request` (blocked → holder),
  `dep-signal` ("my work needs your X first"), `handoff` ("this unit is yours"),
  `done` ("finished `src/auth/**`, released").

## `/handoff` integration

Today `/handoff` writes a handoff file. We extend it so that when fanning a task to N
sessions it:

1. Mints a named board (`MAILBOX_BOARD=handoff-<topic>`).
2. Writes the decomposed work-units into the handoff doc, each tagged with a suggested
   path-scope.
3. Stamps `MAILBOX_BOARD` so each spawned session auto-joins that board.
4. Optionally pre-creates `explicit` claims per unit — staking each session's
   territory *before* it writes a line, so the N sessions are non-overlapping from
   second zero.

For an **agent team** (one session), members share the session's board and use the
same `mailbox` CLI via Bash — in-team and cross-session coordination are the same
mechanism.

## CLI surface

`mailbox <subcommand>` (thin client over the socket):

- `join [--board <name>] [--label <label>]` — register presence (hooks call this).
- `claim <glob...> [--note "..."]` — stake explicit territory.
- `release <glob|claim-id|all> [--force]` — drop a claim.
- `seize <path>` — take over a stale holder's claim.
- `request-release <path>` — message the current holder.
- `send --to <label|*> [--kind <k>] "body"` — message.
- `inbox` — show pending/unread messages.
- `claims [--mine|--all]` — list claims on joined boards.
- `ps` — who's on the board (live/stale, label, cwd).
- `board` — current board info.
- `whoami` — this session's identity.

## Hooks (the ambient layer)

| Hook | Action |
|------|--------|
| `SessionStart` | auto-spawn daemon if down; `join` repo board (+ `MAILBOX_BOARD` if set) |
| `PreToolUse` (Edit/Write/MultiEdit/NotebookEdit) | claim check → allow/deny/warn + auto-claim |
| `PostToolUse` (*) | heartbeat + poll inbox → inject messages |
| `UserPromptSubmit` | heartbeat + poll inbox → inject messages |
| `SessionEnd` | `leave`: mark offline, release `auto` claims |

All hooks fail-open: any internal error logs and allows the operation.

## Error handling

- **Daemon down:** clients auto-spawn it; if spawn fails, hooks fail-open (allow + log).
- **Crash recovery:** daemon reloads `state/` on boot; atomic temp+rename → no
  half-written records.
- **Stale/dead sessions:** server-side heartbeat timeout downgrades claims to warn;
  `SessionEnd` releases `auto` claims; GC reaps offline presence.
- **TOCTOU on simultaneous auto-claim:** single-writer daemon serializes claim checks,
  so "both grab the same path" can't happen — the second caller sees the first claim.
- **Socket protocol:** newline-delimited JSON; unknown/malformed request → error
  reply, never a crash.

## Testing (TDD)

- **Unit:** glob match/overlap, liveness calc, claim conflict resolution (live→deny,
  stale→warn), message routing + `read_by`, atomic write, board derivation from git
  root.
- **Integration:** spin up the daemon on a temp socket, simulate 2+ sessions (distinct
  ids) → assert deny-on-live-conflict, warn-on-stale, auto-claim creation, co-location
  notice, message delivery + read receipts, `SessionEnd` release, crash-reload of
  `state/`.

## Out of scope (v1)

- Daemon-push to idle sessions (turn-boundary pull is enough for v1).
- Cross-machine coordination (local-only).
- A GUI/dashboard; `mailbox ps`/`claims`/`inbox` are CLI-only.
