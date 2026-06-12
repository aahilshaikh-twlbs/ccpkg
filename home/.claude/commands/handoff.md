---
description: Create a structured, segmented handoff file for continuing work in a new session (context running low)
---

# Session Handoff

We are switching to a new session because context is running low. Your job is to produce a **single, exhaustive, well-structured handoff document** so that one or more fresh sessions can resume this work with zero loss of fidelity.

## Inputs you MUST use

1. **The ENTIRE conversation transcript** between the user and Claude Code for this session — every request, decision, dead-end, correction, and the reasoning behind them. Do not summarize away the "why." Capture intent, not just outcomes.
2. **The current state of ALL relevant files** — read them as needed to record exact paths, key symbols, and what is done vs. in-flight vs. untouched. Cite real `file_path:line` references.

## Core requirement: SEGMENTATION

The handoff MUST be divided into **independently consumable segments**. The user may hand **one segment to one new session and a different segment to another**. Therefore:

- Each segment must **stand on its own**. A reader given ONLY that segment (plus the shared Orientation segment) must be able to continue that thread of work.
- Segments must be **scoped by workstream / concern / sub-task**, not by chronology. Group related work together regardless of when it happened in the session.
- If a segment depends on another, state the dependency explicitly at the top of the segment (`Depends on: §2`). Minimize cross-dependencies — prefer duplicating a small amount of context over creating a hidden coupling.
- Give each segment a stable anchor (`## §N — <Title>`) so the user can reference "send §3."

## Required structure

Write the document in this exact order:

```
# Handoff — <one-line mission> — <YYYY-MM-DD>

## §0 — Orientation (read this first, always)
- Mission / overall goal of the work
- Project root, stack, how to run / test / build
- Current overall status in 3–5 bullets
- Map of segments below, each with a one-line "hand this to a session if you need to: …"
- Global conventions, constraints, and hard-won gotchas that apply everywhere
- **Mboard board:** `MBOARD_BOARD=handoff-<YYYY-MM-DD>-<topic-slug>` — the shared coordination board every spawned session joins. State the exact slug here so each segment's bootstrap can reference it. (See "Mboard coordination (multi-session)" below.)

## §1 — <Workstream title>
Status: <not-started | in-progress | blocked | done-pending-verification>
Depends on: <none | §N>

### Goal
What this segment's work is trying to achieve and WHY.

### Context & decisions
The relevant history from the transcript: what was tried, what was chosen, what was rejected and why. Preserve intent.

### Files & key locations
- `path/to/file.ext:line` — what it is, what changed / needs to change

### State: done / in-flight / not-started
Concrete, honest accounting. If something is half-done, say exactly where it stops.

### Next actions
Numbered, specific, executable steps to resume.

### Gotchas & open questions
Traps, unresolved decisions, things the user still needs to answer.

## §2 — <next workstream> …
(repeat the segment template)

## Appendix — Verbatim references
Exact commands, error messages, config snippets, or API contracts worth quoting literally.
```

## Quality bar

- **Faithful, not flattering.** Report what's actually done vs. claimed. If tests weren't run, say so. If something is broken or uncertain, flag it.
- **Specific over vague.** Real paths, real line numbers, real command strings. No "update the relevant config."
- **Preserve reasoning.** A future session should understand not just the current state but why decisions were made, so it doesn't re-litigate settled questions or repeat dead-ends.
- **No filler.** Every line should earn its place in a context-constrained resume.

## Mboard coordination (multi-session)

When this handoff fans work out to **more than one** fresh session, those sessions are otherwise blind to each other and will clobber each other's files. Mboard (the ambient cross-session coordinator installed under `~/.claude/mboard`) makes the fan-out safe: every session that joins the same board sees the others' presence, holds file claims, and exchanges coordination messages. Wire it into the handoff as follows.

### 1. Mint one shared board for the whole handoff
Pick a board slug of the form `handoff-<YYYY-MM-DD>-<topic-slug>` (e.g. `handoff-2026-06-03-auth-refactor`). Use today's date and a short kebab-case topic. Record this exact slug in **§0 — Orientation** (the "Mboard board" bullet). All segments share this one board so they can coordinate; per-segment isolation comes from non-overlapping **claims**, not from separate boards.

### 2. Give every segment a bootstrap block
At the top of each segment that will be handed to its own session, include a fenced `bash` block titled "Bootstrap (run first)" with these exact commands, filled in for that segment:

```bash
# Bootstrap (run first) — joins the shared Mboard board and stakes this segment's territory
export MBOARD_BOARD=handoff-<YYYY-MM-DD>-<topic-slug>   # so SessionStart auto-joins the board
# SessionStart reads MBOARD_BOARD only at session start. On a freshly spawned session the
# export above is enough. If you paste this into an ALREADY-running session (SessionStart
# already fired), run the next line to join the board now:
mboard join --board handoff-<YYYY-MM-DD>-<topic-slug>   # idempotent; no-op if already joined
mboard claim <glob1> <glob2> --note "<segment title>"   # stake this segment's files
mboard ps                                               # see who else is on the board
```

- `export MBOARD_BOARD=<slug>` MUST use the **same slug** recorded in §0 for every segment.
- The globs passed to `mboard claim` MUST be exactly this segment's **"Files & key locations"** paths — that section doubles as the claim scope. Claims across segments MUST NOT overlap (that is what keeps the sessions from colliding).
- The `--note` text should name the segment so a colliding session sees who holds the path and why.

### 3. Coordinate during the work, do not pre-claim
We do **NOT** pre-create owner-less claims in the handoff doc — each session claims its own territory on bootstrap (step 2), so the claim is owned by a live session and is released cleanly when that session leaves. During the work, instruct each segment to coordinate via the `mboard` CLI rather than guessing:

- `mboard ps` — who else is active on the board and where.
- `mboard inbox` — read coordination messages addressed to you (also surfaced automatically after tool use / prompts).
- `mboard send --to <label|*> --kind <note|release-request|dep-signal|handoff|done> "<body>"` — signal another session. Use `note` for general coordination, `dep-signal` for "my work needs your X first", `handoff` to pass a unit on, and `done` when a unit is finished.
- If blocked on a file another session holds, prefer `mboard request-release <path>` — it finds the current holder and sends them a `release-request` message for you (you do NOT need to know the holder's label, and you do NOT send the `release-request` kind manually). Use `mboard seize <path>` only if the holder is stale/offline.

### 4. Add a one-line pointer to §0
In the §0 segment map, after listing the segments, add: "All sessions: run your segment's Bootstrap block first (it joins board `handoff-<YYYY-MM-DD>-<topic-slug>` and claims your files); coordinate via `mboard ps|inbox|send`."

## Output

Write the document to `handoffs/handoff-<YYYY-MM-DD>-<short-slug>.md` relative to the current working directory (create the `handoffs/` directory if needed; if the CWD is not writable or not a project, fall back to `~/handoffs/`). Use a slug derived from the mission.

After writing, print:
1. The absolute path to the file.
2. The segment map (§N — title — "hand to a session for …") so the user can immediately decide what to route where.
