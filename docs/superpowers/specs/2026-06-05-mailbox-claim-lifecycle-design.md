# Mailbox single-source consolidation + claim-lifecycle fix — design (Spec B)

**Date:** 2026-06-05
**Status:** approved-pending-review
**Layer:** base (vendored mailbox is part of the shareable base)

## Background

The mailbox is a vendored, $HOME-relative coordinator that lets **multiple Claude
Code sessions working the same directory** (and, in practice, leader agents of
different agent-*teams*) avoid clobbering each other's files. Its purpose is
**cross-session / cross-team** coordination. It is *not* meant to police
collaboration *within* a single team in a single session — Claude's native agent-
team features (shared task list, ownership) already handle that well.

Two problems block that purpose today.

### Problem 1 — two sources of truth (consolidation)

- Live `~/.claude/mailbox/{hooks,mailbox}` are symlinks into the **standalone**
  repo `~/Documents/Code/mailbox`, *not* into ccpkg's vendored `mailbox/`.
- ccpkg's vendored `mailbox/` is **content-identical** to the standalone for all
  source (engine, hooks, bin, config checksums match). Only `install.py` and one
  plan doc differ — and the **vendored `install.py` is the better one** (portable
  `$HOME`-relative hook commands vs the standalone's baked-in absolute path).
- So the running daemon + hooks are driven by the standalone while ccpkg's copy
  sits unused. There must be exactly one source: the **ccpkg vendored** copy,
  which is also what `ccpkg/mailbox_install.py` already installs from
  (`mailbox_src(root) = root/mailbox`).

### Problem 2 — auto-claims are session-lifetime, not edit-lifetime (the bug)

- `check_write` (`mailbox/src/mailbox/engine.py:243-275`) gives each session one
  `auto` claim and appends every file it ever edits to it, bumping `expires`.
- `heartbeat` (`engine.py:171-176`), fired each `UserPromptSubmit`, refreshes
  that claim's TTL indefinitely — an active session's auto-claims never expire.
- Claims only release on `leave` (`engine.py:185-188`), which only fires at
  `SessionEnd`.

Net: a session accumulates a claim over *every file it has ever touched* and
holds it until the whole session dies. A long-lived leader in session 1 thus
permanently blocks a leader in session 2 from any file it once edited — a
self-deadlock that defeats the mailbox's cross-session purpose. (The same
mechanism forced file-partitioning during the Spec A team build.)

The engine already has inert scaffolding for team-awareness (`Presence.team` /
`Presence.member` in `models.py:14-15`, accepted by `join()`), but the
SessionStart hook never populates it and `check_write` is team-blind. We are
**not** building team-aware enforcement here: there is no reliable `CLAUDE_TEAM`
env var exposed to hooks, so the identity plumbing is fragile. The turn-end
release fix below resolves the deadlock without needing team identity.

## Ordering (locked)

1. **Phase 0 — Consolidation (operational, FIRST).** Collapse to the single
   ccpkg-vendored source and retire the standalone, so the claim fix is made in
   exactly one canonical place and no file is edited mid-re-point.
2. **Phase 1+ — Claim-lifecycle fix (TDD code, SECOND).** Implemented in the
   vendored `mailbox/`, then re-installed so live picks it up.

---

## Phase 0 — Consolidation runbook

Safe ordering; live never hard-breaks (all hooks fail open).

1. **Confirm vendored is canonical.** Verify `mailbox/` source matches the
   standalone (it does). Keep the vendored `install.py` (portable hook paths).
   Reconcile the one differing plan doc by keeping the vendored version (or
   copying the standalone's if newer — to be decided at execution by diffing).
   Commit any vendored doc update.
2. **Re-point live → vendored.** Run `python3 -m ccpkg install` (idempotent;
   `mailbox_install.py` symlinks `~/.claude/mailbox/{hooks,mailbox}` →
   `mailbox/{hooks,bin/mailbox}` and de-dupes the mailbox hook entries in
   settings). Confirm the symlinks now resolve into `…/ccpkg/mailbox`.
3. **Restart the daemon from the vendored bin.** Stop the running daemon
   (terminate the pid in `~/.claude/mailbox/mailboxd.pid` / remove the stale
   `.sock`) so the next hook call respawns it from the vendored `bin/mailbox`.
   Verify with `mailbox ps` / `mailbox claims`.
4. **Functional smoke check.** Confirm presence/claims/messaging work end to end
   against the vendored daemon.
5. **Delete the standalone.** Before removing `~/Documents/Code/mailbox`, confirm
   it has no unpushed commits worth keeping (`git -C … status`/`log @{u}..`); if
   it does, surface them. Then delete the directory. This step is destructive and
   will be re-confirmed with the user at execution time.

**Acceptance:** `readlink ~/.claude/mailbox/hooks` and `…/mailbox` both resolve
under `…/ccpkg/mailbox`; the daemon runs from the vendored bin; `mailbox ps`
works; `~/Documents/Code/mailbox` no longer exists; `ccpkg doctor`/`status`
reports the mailbox healthy.

---

## Phase 1+ — Claim-lifecycle fix (turn-end release)

A session holds `auto` claims only for the turn it is actively editing in; the
claims release when that turn ends. Explicit claims and presence are untouched.

### Components

1. **`engine.release_auto(session_id)`** (new method, `engine.py`):

   ```python
   def release_auto(self, session_id):
       for c in self.claims.values():
           if (c.session_id == session_id and c.kind == "auto"
                   and not c.released):
               c.released = True
               self._persist_claim(c)
       return {"ok": True}
   ```

   - Releases only `kind == "auto"` claims; leaves `explicit` claims held
     (deliberate holds must survive a turn boundary).
   - Does **not** touch `Presence` — the session stays `active`; it has merely
     finished a turn, not departed. (Contrast `leave()`, which goes offline and
     drops everything.)

2. **Protocol + dispatch.** Register the `release_auto` action in
   `mailbox/src/mailbox/protocol.py` and route it to `engine.release_auto` in the
   server/daemon dispatch (mirroring how `leave` / `heartbeat` are wired).

3. **`Stop` hook** (`mailbox/hooks/stop.py`, new): reads `session_id` from stdin
   JSON, calls `client.request("release_auto", {"session_id": sid})`. Fail-open
   ALWAYS (any error → exit 0), matching the other hooks' contract and the
   `sys.path`-bootstrap preamble used by `session_end.py`.

4. **Heartbeat unchanged.** After a turn's auto-claims release, the heartbeat
   refresh loop simply finds nothing to refresh until the next edit creates a
   fresh claim. Minimal blast radius; no change needed.

### Hook registration (three places — keep consistent)

The new `Stop` hook must be registered everywhere mailbox hooks are declared:
- `ccpkg/mailbox_install.py` — the `(event, matcher, script)` hook list.
- `mailbox/install.py` — the mailbox's own installer hook list.
- `home/.claude/settings.json` — the static repo settings (merge-mode) that
  ccpkg deep-merges into live.

(The plan will read all three lists first to match their exact shapes.)

### Data flow (one turn, post-fix)

```
UserPromptSubmit ─ heartbeat (nothing to refresh) ─► turn runs
        │
   Edit/Write ─► PreToolUse check_write ─► creates/extends this session's auto-claim (holds file)
        │
      Stop ─► release_auto(session_id) ─► this session's auto-claims released
        │
   next turn: another session may now claim those files
```

### Error handling

- `stop.py` fails open on empty/malformed stdin, missing `session_id`, or any
  exception → exit 0, no effect, never blocks.
- `release_auto` on a session with no auto-claims is a no-op returning `{"ok": True}`.
- Concurrent release + check_write are serialized by the daemon's single-threaded
  request loop (same as today's `leave`/`check_write`).

### Testing (mailbox suite — stdlib + pytest via repo `.venv`)

- `test_engine_claims.py`: `release_auto` releases `auto` claims, **keeps**
  `explicit` claims, and **leaves presence `active`**.
- `test_engine_checkwrite.py`: after session A `release_auto`, session B's
  `check_write` on a file A previously held returns `allow` (was `deny`).
- `test_protocol.py` / server test: the `release_auto` action round-trips through
  protocol + dispatch to the engine method.
- `test_hooks.py`: `stop.py` invoked with a valid `Stop` payload issues a
  `release_auto` request; invoked with empty/malformed stdin exits 0 with no
  request (fail-open).
- Regression: full mailbox suite stays green; `ccpkg` suite stays green.

**Acceptance:** with the fixed vendored mailbox installed, two sessions editing
the same file no longer deadlock across turns — session B can write a file after
session A's turn ends — while same-turn protection still denies a simultaneous
write.

## Out of scope

- **Team-aware enforcement** (same-team members never block each other). The
  scaffolding exists but the identity plumbing is unreliable; turn-end release
  fixes the deadlock without it. Revisit only if turn-end release proves
  insufficient in practice.
- **Merging `feat/nuke-mode`** and any PR work — deferred to after both phases.
