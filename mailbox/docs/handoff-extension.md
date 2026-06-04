# Handoff Extension — Mailbox Coordination

This document captures the exact additions required by **Contract §15** to extend the
`/handoff` skill so that multi-session fan-outs are safe and coordinated via Mailbox.

---

## How to apply

**Do not edit `~/.claude/commands/handoff.md` directly from this repo.**  Open that file
in your editor (or via the `handoff` skill source) and make the two edits described below
exactly as written.  The edits are idempotent: if either string already appears verbatim,
skip that step.

### Edit A — Add the "Mailbox board" bullet to §0 Orientation in the template

Locate the last bullet inside the `## §0 — Orientation (read this first, always)` block
**within the fenced `## Required structure` template**.  The current last bullet is:

```
- Global conventions, constraints, and hard-won gotchas that apply everywhere
```

Append the following line immediately after it (keep indentation consistent with the
surrounding list):

```
- **Mailbox board:** `MAILBOX_BOARD=handoff-<YYYY-MM-DD>-<topic-slug>` — the shared coordination board every spawned session joins. State the exact slug here so each segment's bootstrap can reference it. (See "Mailbox coordination (multi-session)" below.)
```

### Edit B — Insert the new top-level section before `## Output`

Locate the exact line `## Output` followed by:

```
Write the document to `handoffs/handoff-<YYYY-MM-DD>-<short-slug>.md` relative to the current working directory
```

Insert the entire block below **immediately before** `## Output` (the `## Output` heading
and its content remain unchanged after the new block):

---

## Mailbox coordination (multi-session)

When this handoff fans work out to **more than one** fresh session, those sessions are otherwise blind to each other and will clobber each other's files. Mailbox (the ambient cross-session coordinator installed under `~/.claude/mailbox`) makes the fan-out safe: every session that joins the same board sees the others' presence, holds file claims, and exchanges coordination messages. Wire it into the handoff as follows.

### 1. Mint one shared board for the whole handoff
Pick a board slug of the form `handoff-<YYYY-MM-DD>-<topic-slug>` (e.g. `handoff-2026-06-03-auth-refactor`). Use today's date and a short kebab-case topic. Record this exact slug in **§0 — Orientation** (the "Mailbox board" bullet). All segments share this one board so they can coordinate; per-segment isolation comes from non-overlapping **claims**, not from separate boards.

### 2. Give every segment a bootstrap block
At the top of each segment that will be handed to its own session, include a fenced `bash` block titled "Bootstrap (run first)" with these exact commands, filled in for that segment:

```bash
# Bootstrap (run first) — joins the shared Mailbox board and stakes this segment's territory
export MAILBOX_BOARD=handoff-<YYYY-MM-DD>-<topic-slug>   # so SessionStart auto-joins the board
# SessionStart reads MAILBOX_BOARD only at session start. On a freshly spawned session the
# export above is enough. If you paste this into an ALREADY-running session (SessionStart
# already fired), run the next line to join the board now:
mailbox join --board handoff-<YYYY-MM-DD>-<topic-slug>   # idempotent; no-op if already joined
mailbox claim <glob1> <glob2> --note "<segment title>"   # stake this segment's files
mailbox ps                                               # see who else is on the board
```

- `export MAILBOX_BOARD=<slug>` MUST use the **same slug** recorded in §0 for every segment.
- The globs passed to `mailbox claim` MUST be exactly this segment's **"Files & key locations"** paths — that section doubles as the claim scope. Claims across segments MUST NOT overlap (that is what keeps the sessions from colliding).
- The `--note` text should name the segment so a colliding session sees who holds the path and why.

### 3. Coordinate during the work, do not pre-claim
We do **NOT** pre-create owner-less claims in the handoff doc — each session claims its own territory on bootstrap (step 2), so the claim is owned by a live session and is released cleanly when that session leaves. During the work, instruct each segment to coordinate via the `mailbox` CLI rather than guessing:

- `mailbox ps` — who else is active on the board and where.
- `mailbox inbox` — read coordination messages addressed to you (also surfaced automatically after tool use / prompts).
- `mailbox send --to <label|*> --kind <note|release-request|dep-signal|handoff|done> "<body>"` — signal another session. Use `note` for general coordination, `dep-signal` for "my work needs your X first", `handoff` to pass a unit on, and `done` when a unit is finished.
- If blocked on a file another session holds, prefer `mailbox request-release <path>` — it finds the current holder and sends them a `release-request` message for you (you do NOT need to know the holder's label, and you do NOT send the `release-request` kind manually). Use `mailbox seize <path>` only if the holder is stale/offline.

### 4. Add a one-line pointer to §0
In the §0 segment map, after listing the segments, add: "All sessions: run your segment's Bootstrap block first (it joins board `handoff-<YYYY-MM-DD>-<topic-slug>` and claims your files); coordinate via `mailbox ps|inbox|send`."

---

*(End of content to insert before `## Output`)*
