# Nuke Mode — design (Spec A)

**Date:** 2026-06-05
**Status:** approved-pending-review
**Layer:** base (shareable; no PII/company-specifics/secrets)

## Problem

There is no single switch that puts a Claude Code session into "maximum-effort"
mode. Today you'd hand-type `ultrathink`/`ultracode` each turn and remember to
prefer agent teams over subagents. Nuke mode makes that a one-shot arm that
sticks for the rest of the session.

When armed, every remaining turn this session should operate as:

- **ultracode** — author and run Workflows by default for substantive work;
  token cost is not a constraint.
- **ultrathink** — reason as deeply as the task warrants before acting.
- **ultraplan** — (keyword) plan first, exhaustively, before executing.
- **Execution model** — the **Workflow** tool is the orchestration + *read-only*
  analysis brain (research, review, audit fan-out). **All execution and
  implementation work goes to persistent, mailbox-coordinated agent teams**
  (`TeamCreate` + `SendMessage`). Build work is **never** handed to ephemeral
  Workflow subagents.

## Why a command alone can't do this

A Claude Code slash command is a **one-shot prompt expansion** — it injects text
into a single turn and is then gone. It holds no state across turns, so it
cannot by itself make a mode persist "for the remainder of the session." Session
persistence requires a **hook** that re-injects the directive every turn. The
repo already runs a `UserPromptSubmit` hook chain (the mailbox
`user_prompt_submit.py`) that injects context each turn — that is the natural
hook point.

## Architecture

The hook is the source of truth; the command is just an arming trigger.

```
/nuke  ──expands to──►  body containing sentinel  <<NUKE-ARM>>
                                    │
                         UserPromptSubmit fires (same turn)
                                    │
                    nuke.py reads stdin {session_id, prompt, hook_event_name}
                                    │
        sentinel present? ──► write ~/.claude/nuke/<session_id>.flag
                                    │
        flag exists? ──► print NUKE directive to stdout (becomes context)
                                    │
                      ...repeats every turn while flag lives...
                                    │
              SessionEnd fires ──► nuke.py deletes the flag
```

- **State location:** `~/.claude/nuke/<session_id>.flag` — runtime state, **not**
  committed to the repo. Keyed by `session_id` so concurrent sessions can't
  cross-contaminate, and a fresh session starts disarmed.
- **Arming:** done by the hook (which receives `session_id` on stdin), triggered
  by the `<<NUKE-ARM>>` sentinel the command injects. The command never needs to
  know its own `session_id`.
- **Single source of truth:** the full directive text lives only in `nuke.py`.
  The command body does not restate it, so the arming turn and every later turn
  receive identical injected text (DRY). The hook fires on the same
  `UserPromptSubmit` as the `/nuke` invocation, so the directive is present on
  the arming turn too.
- **Disarm:** arm-only by design (no `/nuke off`). The flag is deleted by the
  `SessionEnd` hook. Once armed, the session stays in nuke mode until it ends —
  this is the accepted cost trade-off.

## Components

Four files (one new dir of runtime state created at runtime):

1. **`home/.claude/commands/nuke.md`** — slash command. Minimal body: a one-line
   `🔴 arming nuke mode` confirmation plus the literal `<<NUKE-ARM>>` sentinel.
   Frontmatter `description:` following the `create-prd.md` pattern.

2. **`home/.claude/hooks/nuke.py`** — no-third-party-dependency Python 3
   (system `python3` >= 3.9), matching the repo's no-deps constraint. Branches on
   `hook_event_name` from stdin JSON:
   - `UserPromptSubmit`: `mkdir -p ~/.claude/nuke`; if the prompt contains
     `<<NUKE-ARM>>`, create the flag; if the flag exists, print the directive
     block to stdout.
   - `SessionEnd`: delete `~/.claude/nuke/<session_id>.flag`.
   - **Fail-open always** — any error exits 0 and never blocks a turn, matching
     the mailbox hooks' contract.

3. **`home/.claude/settings.json`** — append `nuke.py` to the existing
   `UserPromptSubmit` chain (after the mailbox hook) and add a `SessionEnd` entry
   (a new event in this file's `hooks` map). Invocation form mirrors the mailbox
   hooks: `python3 $HOME/.claude/hooks/nuke.py`.

4. **`manifest.json`** — two new entries:
   - `home/.claude/commands/nuke.md` → mode `symlink`, os `any`, layer `base`.
   - `home/.claude/hooks/nuke.py` → mode `symlink`, os `any`, layer `base`.

## Injected directive (authored in `nuke.py`)

Emitted verbatim each armed turn (wrapped in a `<system-reminder>` block so it
reads as harness context, consistent with how ultracode/ultrathink surface):

> 🔴 **NUKE MODE ACTIVE** — every remaining turn this session:
> - **ultracode ON** — author and run Workflows by default for substantive work;
>   token cost is not a constraint.
> - **ultrathink** — reason as deeply as the task warrants before acting.
> - **ultraplan** — plan first, exhaustively, before executing.
> - **Execution model** — Workflow orchestrates and runs *read-only* analysis
>   fan-out (research/review/audit). **All execution/implementation goes to
>   persistent agent teams** (`TeamCreate` + mailbox `SendMessage`). Never hand
>   build work to ephemeral subagents.

The literal keywords `ultracode`, `ultrathink`, `ultraplan` are included in the
injected text so the harness's own keyword detection has a chance to engage.

### Known limitation (accepted)

Hook-injected text may **not** trigger the harness's *native* `ultracode` /
`ultrathink` detection — that detector likely scans the user's typed prompt, not
hook-supplied context. Per decision, nuke mode relies on the **behavioral
directive** (instructing Claude to act as if those modes are on) and does **not**
attempt to verify native detection. If the keywords also trigger native behavior,
that is a bonus, not a dependency.

## Error handling

- Hook fails open: malformed/empty stdin, missing `session_id`, unwritable state
  dir, or any exception → exit 0, inject nothing, block nothing.
- Missing state dir is created on demand (`mkdir -p`).
- A stale flag from a crashed prior session cannot leak into a new one because
  the flag is keyed by the live `session_id`.

## Testing

- **Arming:** stdin with `UserPromptSubmit` + a prompt containing `<<NUKE-ARM>>`
  → flag file created; stdout contains the directive.
- **Sticky:** subsequent `UserPromptSubmit` with no sentinel but flag present →
  stdout still contains the directive.
- **Disarmed by default:** `UserPromptSubmit`, no sentinel, no flag → empty
  stdout, exit 0.
- **Session isolation:** flag for session A does not cause injection for session
  B.
- **Clear:** `SessionEnd` for a session → its flag is removed.
- **Fail-open:** empty stdin / malformed JSON / missing `session_id` → exit 0,
  no output, no crash.
- **`ccpkg` integration:** after adding manifest entries, `ccpkg pull` symlinks
  the command + hook; `ccpkg doctor`/`status` reports no drift; `ccpkg scan`
  passes (base-purity + secrets).

## Out of scope (follow-on: Spec B)

The mailbox auto-claim lifecycle bug — auto-claims are session-scoped and
heartbeat-refreshed, so a teammate holds every file it ever edited for its whole
life, deadlocking multi-phase agent-team runs (`engine.py:243-275`, `171-176`,
`185-188`). Nuke mode leans hard on agent teams, so this matters, but it is an
independent subsystem with its own test surface (`test_engine_claims.py`,
`test_engine_gc.py`). It gets its own design → plan → build cycle. Chosen fix
direction: release a session's auto-claims on **turn end** (a `Stop` hook →
auto-only release) so a teammate holds a file only while actively editing across
that turn, not for its whole session.
