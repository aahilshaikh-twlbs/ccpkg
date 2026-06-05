# Mailbox Consolidation + Claim-Lifecycle Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the mailbox to a single source (ccpkg-vendored), then fix session-lifetime auto-claims so a session holds files only for the turn it's actively editing — unblocking cross-session/cross-team coordination.

**Architecture:** Phase 0 re-points live `~/.claude/mailbox` from the standalone repo to ccpkg's vendored `mailbox/` and retires the standalone. Phase 1 extends the existing `engine.release` op with an `"auto"` selector and adds a `Stop` hook that calls it at turn end, releasing only auto-claims while leaving explicit claims and presence intact.

**Tech Stack:** Python 3.9+ stdlib only, Unix-socket daemon + newline-JSON protocol, Claude Code hooks, pytest via the repo `.venv`.

---

## Important environment notes (read once)

- **Branch:** `feat/mailbox-claim-lifecycle` (already checked out, off `main`).
- **pytest is only in the repo `.venv`.** Run the ccpkg suite as `.venv/bin/python -m pytest -q` from repo root. Run the **vendored mailbox** suite as `PYTHONPATH=src ../.venv/bin/python -m pytest -q` from inside `mailbox/` (the stdlib has a `mailbox` module that shadows ours unless `src/` leads `PYTHONPATH`).
- **Known-red baseline:** the vendored mailbox suite currently FAILS exactly one test — `mailbox/tests/test_install.py::test_install_idempotent_preserves_notify_hook` — because the vendored `install.py` emits the `$HOME`-relative hook command but that test still expects the old absolute path. Phase 0 Task 0.1 fixes this so the canonical source is green. Everything else (155 passed, 1 skipped) is green.
- **Design refinement vs spec:** the spec described a new `engine.release_auto` op. Planning found the existing `engine.release(session_id, selector)` already handles `selector="all"` and is already wired through `protocol.OPS`, the daemon dispatch, and the CLI. The DRYer implementation is to add an `"auto"` selector to `release` — identical behavior, zero protocol/CLI/dispatch changes. This plan uses the selector approach.
- **Daemon caches code in memory.** After editing `engine.py`, the running daemon must be restarted to pick up the change (Phase 1 Task 5).

---

## File Structure

| File | Phase | Responsibility |
|------|-------|----------------|
| `mailbox/tests/test_install.py` (modify) | 0 | Fix stale assertion so the canonical vendored source's own suite is green. |
| live `~/.claude/mailbox/*` + daemon (ops) | 0 | Re-point to vendored, restart daemon. No repo files. |
| `~/Documents/Code/mailbox` (delete) | 0 | Retire the standalone source. |
| `mailbox/src/mailbox/engine.py` (modify) | 1 | Add `"auto"` selector to `release`. |
| `mailbox/hooks/stop.py` (create) | 1 | Stop hook → `release(selector="auto")`. Fail-open. |
| `mailbox/tests/test_engine_claims.py` (modify) | 1 | Engine tests for the `"auto"` selector. |
| `mailbox/tests/test_engine_checkwrite.py` (modify) | 1 | Cross-session writability after auto-release. |
| `mailbox/tests/test_hooks.py` (modify) | 1 | Stop-hook behavior + fail-open. |
| `mailbox/install.py` (modify) | 1 | Register `Stop` hook in the mailbox installer list. |
| `ccpkg/mailbox_install.py` (modify) | 1 | Register `Stop` hook in ccpkg's installer list. |
| `home/.claude/settings.json` (modify) | 1 | Static `Stop` hook entry merged into live. |
| `tests/test_mailbox_install.py` (modify) | 1 | Update ccpkg install test for the 6th hook. |
| `mailbox/tests/test_install.py` (modify) | 1 | Update vendored install test for the 6th hook. |

---

# PHASE 0 — Consolidation (ops)

## Task 0.1: Make the canonical vendored source green

**Files:**
- Modify: `mailbox/tests/test_install.py:125`

- [ ] **Step 1: Reproduce the known failure**

Run: `cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest tests/test_install.py::test_install_idempotent_preserves_notify_hook -q`
Expected: FAIL — assertion compares `'python3 "$HOME/.claude/mailbox/hooks/session_start.py"'` against an absolute `/private/tmp/...` path.

- [ ] **Step 2: Fix the assertion to expect the canonical `$HOME` form**

In `mailbox/tests/test_install.py`, replace line 125:

```python
        assert mailbox_cmds[0] == "python3 " + os.path.join(home, "hooks", filename)
```

with:

```python
        assert mailbox_cmds[0] == 'python3 "$HOME/.claude/mailbox/hooks/' + filename + '"'
```

- [ ] **Step 3: Verify that test passes and the full vendored suite is green**

Run: `cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest -q`
Expected: PASS — `156 passed, 1 skipped` (was 155 passed / 1 failed / 1 skipped).

- [ ] **Step 4: Reconcile the one differing doc (keep vendored canonical)**

The only other standalone↔vendored difference is `docs/superpowers/plans/2026-06-03-mailbox.md`. Diff them:

Run: `diff ~/Documents/Code/mailbox/docs/superpowers/plans/2026-06-03-mailbox.md mailbox/docs/superpowers/plans/2026-06-03-mailbox.md`
Decision: keep the **vendored** version as canonical. Only if the standalone contains substantive content absent from the vendored copy, copy it over with `cp ~/Documents/Code/mailbox/docs/superpowers/plans/2026-06-03-mailbox.md mailbox/docs/superpowers/plans/2026-06-03-mailbox.md`. Otherwise make no change.

- [ ] **Step 5: Commit**

```bash
git add mailbox/tests/test_install.py mailbox/docs/superpowers/plans/2026-06-03-mailbox.md
git commit -m "fix(mailbox): vendored install test expects \$HOME-relative hook path

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```
(If Step 4 made no doc change, omit that path from `git add`.)

---

## Task 0.2: Re-point live `~/.claude/mailbox` to the vendored copy

**Files:** none (ops only)

- [ ] **Step 1: Record the current (standalone) wiring**

Run: `readlink ~/.claude/mailbox/hooks; readlink ~/.claude/mailbox/mailbox`
Expected (before): both resolve under `/Users/aahil/Documents/Code/mailbox`.

- [ ] **Step 2: Re-point via ccpkg install**

Run: `.venv/bin/python -m ccpkg install`
Expected: completes; mailbox step reports symlinking `~/.claude/mailbox/{mailbox,hooks}` to the vendored paths. (`mailbox_install.py` backs up any real file before replacing and de-dupes the hook entries in settings.)

- [ ] **Step 3: Verify live now points at the vendored copy**

Run: `readlink ~/.claude/mailbox/hooks; readlink ~/.claude/mailbox/mailbox`
Expected (after): both resolve under `/Users/aahil/Documents/Code/ccpkg/mailbox` (i.e., `…/ccpkg/mailbox/hooks` and `…/ccpkg/mailbox/bin/mailbox`).

---

## Task 0.3: Restart the daemon from the vendored bin

**Files:** none (ops only)

- [ ] **Step 1: Stop the running daemon**

Run:
```bash
[ -f ~/.claude/mailbox/mailboxd.pid ] && kill "$(cat ~/.claude/mailbox/mailboxd.pid)" 2>/dev/null; sleep 1
rm -f ~/.claude/mailbox/mailboxd.sock
```
Expected: no error (a dead pid is fine — it fails open).

- [ ] **Step 2: Respawn from the vendored bin via a request (autospawn)**

Run: `~/.claude/mailbox/mailbox ps`
Expected: prints the presence table (the CLI autospawns the daemon from the now-vendored `bin/mailbox`). A fresh `mailboxd.pid`/`.sock` reappear.

- [ ] **Step 3: Confirm the running daemon binary is the vendored one**

Run: `ps -o command= -p "$(cat ~/.claude/mailbox/mailboxd.pid)"`
Expected: the command path resolves through `…/ccpkg/mailbox` (via the live symlink), not `…/Documents/Code/mailbox`.

---

## Task 0.4: Functional smoke check

**Files:** none (ops only)

- [ ] **Step 1: Exercise presence + claims end to end**

Run: `~/.claude/mailbox/mailbox ps && ~/.claude/mailbox/mailbox claims`
Expected: both commands return without error against the vendored daemon.

- [ ] **Step 2: ccpkg health**

Run: `.venv/bin/python -m ccpkg doctor 2>&1 | tail -20`
Expected: no mailbox-related errors.

---

## Task 0.5: Retire the standalone (DESTRUCTIVE — confirm with user)

**Files:**
- Delete: `~/Documents/Code/mailbox`

- [ ] **Step 1: Verify the standalone has nothing unpushed worth keeping**

Run:
```bash
git -C ~/Documents/Code/mailbox status --short
git -C ~/Documents/Code/mailbox log --oneline @{u}.. 2>/dev/null || echo "(no upstream configured)"
```
Expected: report the output. If there are uncommitted changes or unpushed commits whose content is NOT already in the vendored copy, STOP and surface them to the user before deleting.

- [ ] **Step 2: Re-confirm deletion with the user**

Explicitly ask the user to confirm deleting `~/Documents/Code/mailbox` now that live points at the vendored copy. Do not proceed without confirmation.

- [ ] **Step 3: Delete the standalone**

Run: `rm -rf ~/Documents/Code/mailbox`
Expected: removed.

- [ ] **Step 4: Confirm live still works (symlinks resolve into vendored, not the deleted dir)**

Run: `readlink ~/.claude/mailbox/hooks && ~/.claude/mailbox/mailbox ps`
Expected: symlink resolves under `…/ccpkg/mailbox`; `ps` still works (daemon runs from vendored bin).

---

# PHASE 1 — Claim-lifecycle fix (TDD)

## Task 1: Add the `"auto"` selector to `engine.release`

**Files:**
- Modify: `mailbox/src/mailbox/engine.py` (`release` method, ~line 179)
- Test: `mailbox/tests/test_engine_claims.py`

- [ ] **Step 1: Write the failing tests**

Append to `mailbox/tests/test_engine_claims.py`:

```python
def test_release_auto_releases_only_auto_claims(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    auto = engine.claim("s1", ["/repo/a.py"], kind="auto")
    explicit = engine.claim("s1", ["/repo/b/**"], note="hold", kind="explicit")

    result = engine.release("s1", "auto")

    assert result["released"] == [auto["id"]]
    assert engine.claims[auto["id"]].released is True
    # explicit claim survives the turn boundary
    assert engine.claims[explicit["id"]].released is False


def test_release_auto_keeps_presence_active(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    engine.claim("s1", ["/repo/a.py"], kind="auto")

    engine.release("s1", "auto")

    assert engine.presence["s1"].status == "active"


def test_release_all_still_releases_every_claim(engine, clock):
    clock.t = 1000.0
    _join(engine, "s1", "alice", "/repo")
    c1 = engine.claim("s1", ["/repo/a.py"], kind="auto")
    c2 = engine.claim("s1", ["/repo/b/**"], kind="explicit")

    result = engine.release("s1", "all")

    assert set(result["released"]) == {c1["id"], c2["id"]}
    assert engine.claims[c1["id"]].released is True
    assert engine.claims[c2["id"]].released is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest tests/test_engine_claims.py -k "release_auto or release_all_still" -q`
Expected: FAIL — `release("s1", "auto")` currently falls through to the claim-id branch (selector `"auto"` is treated as a claim id, matches nothing) and releases nothing, so `result["released"]` is `[]`.

- [ ] **Step 3: Extend `release` with the `"auto"` selector**

In `mailbox/src/mailbox/engine.py`, replace the `release` method's `selector == "all"` block. The current method begins:

```python
    def release(self, session_id, selector, force=False):
        released = []
        if selector == "all":
            for c in self.claims.values():
                if c.session_id == session_id and not c.released:
                    c.released = True
                    self._persist_claim(c)
                    released.append(c.id)
            return {"released": released}
```

Replace that `if selector == "all":` block with:

```python
        if selector in ("all", "auto"):
            for c in self.claims.values():
                if c.session_id != session_id or c.released:
                    continue
                if selector == "auto" and c.kind != "auto":
                    continue
                c.released = True
                self._persist_claim(c)
                released.append(c.id)
            return {"released": released}
```

Leave the rest of the method (the claim-id `target` branch) unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest tests/test_engine_claims.py -q`
Expected: PASS (all prior claim tests plus the 3 new ones).

- [ ] **Step 5: Commit**

```bash
git add mailbox/src/mailbox/engine.py mailbox/tests/test_engine_claims.py
git commit -m "feat(mailbox): release(selector=\"auto\") releases only auto-claims

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Cross-session writability after auto-release

**Files:**
- Test: `mailbox/tests/test_engine_checkwrite.py`

- [ ] **Step 1: Write the failing test**

Append to `mailbox/tests/test_engine_checkwrite.py`:

```python
def test_check_write_allowed_after_holder_releases_auto(engine, clock):
    clock.t = 1000.0
    engine.join("s1", "alice", "/repo")
    engine.join("s2", "bob", "/repo")

    # s1 auto-claims a file by writing it; s2 is then denied.
    engine.check_write("s1", "/repo/shared.py")
    denied = engine.check_write("s2", "/repo/shared.py")
    assert denied["decision"] == "deny"
    assert denied["holder"] == "alice"

    # s1's turn ends -> auto-claims released.
    engine.release("s1", "auto")

    # s2 may now write the same file.
    allowed = engine.check_write("s2", "/repo/shared.py")
    assert allowed["decision"] == "allow"
```

- [ ] **Step 2: Run the test to verify it fails, then passes**

Run: `cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest tests/test_engine_checkwrite.py::test_check_write_allowed_after_holder_releases_auto -q`
Expected: PASS — Task 1 already implemented `release("auto")`, so this verifies the cross-session unblock end to end at the engine level. (If Task 1 were absent it would FAIL at the final `allow` assertion, still showing `deny`.)

- [ ] **Step 3: Commit**

```bash
git add mailbox/tests/test_engine_checkwrite.py
git commit -m "test(mailbox): cross-session write allowed after auto-claim release

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: The `Stop` hook

**Files:**
- Create: `mailbox/hooks/stop.py`
- Test: `mailbox/tests/test_hooks.py`

- [ ] **Step 1: Write the failing tests**

Append to `mailbox/tests/test_hooks.py` (this file already defines `_load_hook`, `_run_hook`, `REPO_ROOT`, and uses `tmp_home`):

```python
def test_stop_hook_releases_auto_keeps_presence(tmp_home):
    from mailbox import client

    sid = "sess-stop-1"
    cwd = REPO_ROOT
    client.ensure_running()
    assert client.request("join", {"session_id": sid, "label": "stopper", "cwd": cwd})["ok"]

    target = os.path.join(cwd, "src", "mailbox", "engine.py")
    assert client.request("check_write", {"session_id": sid, "abs_path": target})["data"]["decision"] == "allow"

    # Precondition: one live auto claim, session active.
    mine_before = client.request("list_claims", {"session_id": sid, "scope": "mine"})
    assert len(mine_before["data"]) == 1

    result = _run_hook("stop.py", {"session_id": sid, "cwd": cwd, "hook_event_name": "Stop"})
    assert result.returncode == 0

    # Auto claim released (list_claims omits released claims) but presence stays active.
    mine_after = client.request("list_claims", {"session_id": sid, "scope": "mine"})
    assert mine_after["data"] == []
    who = client.request("whoami", {"session_id": sid})
    assert who["data"]["status"] == "active"


def test_stop_hook_fail_open_on_empty_stdin(tmp_home):
    result = _run_hook("stop.py", None)
    assert result.returncode == 0
```

Note: `_run_hook("stop.py", None)` must send empty stdin. If the existing `_run_hook` helper JSON-encodes its payload, pass `{}` instead and confirm the hook still exits 0; if it supports `None`/raw, prefer empty input. Inspect `_run_hook`'s signature at the top of `test_hooks.py` and match it (do NOT change the helper).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest tests/test_hooks.py -k stop_hook -q`
Expected: FAIL — `hooks/stop.py` does not exist yet (`_load_hook`/`_run_hook` cannot find it).

- [ ] **Step 3: Create the Stop hook (mirrors `session_end.py`)**

Create `mailbox/hooks/stop.py`:

```python
#!/usr/bin/env python3
"""Stop hook: release this session's AUTO claims at turn end (presence stays active).

Turn-end release: a session holds auto-claims only while actively editing within a
turn. When the turn ends, free them so other sessions/teams working the same dir can
claim those files. Explicit claims and presence are left intact (unlike SessionEnd's
`leave`, which goes offline and drops everything).

Fail-open ALWAYS: any error exits 0 silently and never blocks work.
"""
import json
import os
import sys

# Make the repo's src/ importable when running uninstalled (Contract §13).
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    try:
        sid = payload.get("session_id")
        if not sid:
            return 0
        from mailbox import client
        client.request("release", {"session_id": sid, "selector": "auto"})
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest tests/test_hooks.py -k stop_hook -q`
Expected: PASS (both stop-hook tests).

- [ ] **Step 5: Commit**

```bash
git add mailbox/hooks/stop.py mailbox/tests/test_hooks.py
git commit -m "feat(mailbox): Stop hook releases auto-claims at turn end

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Register the `Stop` hook in all three installers + their tests

**Files:**
- Modify: `mailbox/install.py` (hook list, ~line 27-31)
- Modify: `ccpkg/mailbox_install.py` (`HOOKS`, ~line 19-25)
- Modify: `home/.claude/settings.json` (`hooks.Stop`)
- Modify: `mailbox/tests/test_install.py` (~line 104, 117)
- Modify: `tests/test_mailbox_install.py` (`HOOK_SCRIPTS`, ~line 17; comment ~line 99)

- [ ] **Step 1: Update the install tests first (they will fail, proving coverage)**

In `tests/test_mailbox_install.py`, add a `Stop` entry to the `HOOK_SCRIPTS` dict (after the `SessionEnd` line, ~line 17):

```python
    "SessionEnd": (None, "session_end.py"),
    "Stop": (None, "stop.py"),
}
```

And update the comment at ~line 99 from "all 5 hooks" to "all 6 hooks".

In `mailbox/tests/test_install.py`, add `"Stop"` to the event tuple (~line 104):

```python
    for event in ("SessionStart", "PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionEnd", "Stop"):
```

and add to the `expected` dict (~line 117, after `SessionEnd`):

```python
        "SessionEnd": "session_end.py",
        "Stop": "stop.py",
    }
```

- [ ] **Step 2: Run both install tests to verify they fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_mailbox_install.py -q
cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest tests/test_install.py -q; cd ..
```
Expected: FAIL — the installers don't wire a `Stop` hook yet, so the tests can't find `stop.py` for the `Stop` event.

- [ ] **Step 3: Register the hook in the mailbox installer**

In `mailbox/install.py`, the hook list (lines ~27-31) currently ends with the `SessionEnd` tuple. Add a `Stop` tuple after it:

```python
    ("SessionEnd", None, "session_end.py"),
    ("Stop", None, "stop.py"),
```

- [ ] **Step 4: Register the hook in ccpkg's installer**

In `ccpkg/mailbox_install.py`, update the `HOOKS` list (lines ~19-25). Change the leading comment from "The 5 mailbox hooks" to "The 6 mailbox hooks" and add the `Stop` tuple after `SessionEnd`:

```python
    ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit", "pre_tool_use.py"),
    ("SessionEnd", None, "session_end.py"),
    ("Stop", None, "stop.py"),
]
```

- [ ] **Step 5: Add the static `Stop` entry to repo settings**

In `home/.claude/settings.json`, the `hooks.Stop` array currently contains only the notify hook group. Append a mailbox group so it reads:

```json
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "[ -n \"$SUPERSET_HOME_DIR\" ] && [ -x \"$SUPERSET_HOME_DIR/hooks/notify.sh\" ] && \"$SUPERSET_HOME_DIR/hooks/notify.sh\" || true"
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $HOME/.claude/mailbox/hooks/stop.py"
          }
        ]
      }
    ],
```

Validate it parses:

Run: `python3 -c "import json; json.load(open('home/.claude/settings.json')); print('ok')"`
Expected: `ok`

- [ ] **Step 6: Run both install tests to verify they pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_mailbox_install.py -q
cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest tests/test_install.py -q; cd ..
```
Expected: PASS for both.

- [ ] **Step 7: Commit**

```bash
git add mailbox/install.py ccpkg/mailbox_install.py home/.claude/settings.json mailbox/tests/test_install.py tests/test_mailbox_install.py
git commit -m "feat(mailbox): register Stop hook in installers + static settings

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Re-install, restart daemon, full verification

**Files:** none (ops + verification)

- [ ] **Step 1: Full ccpkg suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all green, including updated `test_mailbox_install.py`).

- [ ] **Step 2: Full vendored mailbox suite**

Run: `cd mailbox && PYTHONPATH=src ../.venv/bin/python -m pytest -q; cd ..`
Expected: PASS (all green, including new engine/checkwrite/hook tests and updated `test_install.py`).

- [ ] **Step 3: Re-install so live gets the Stop hook**

Run: `.venv/bin/python -m ccpkg install`
Expected: completes; `~/.claude/mailbox/hooks/stop.py` now exists (the hooks dir is symlinked to the vendored copy, which now contains `stop.py`), and live `settings.json` carries the mailbox `Stop` hook.

Verify:
```bash
ls -l ~/.claude/mailbox/hooks/stop.py
python3 -c "import json,os; s=json.load(open(os.path.expanduser('~/.claude/settings.json'))); print(any('mailbox/hooks/stop.py' in h.get('command','') for g in s['hooks'].get('Stop',[]) for h in g['hooks']))"
```
Expected: the file lists; the print outputs `True`.

- [ ] **Step 4: Restart the daemon so it runs the new engine code**

Run:
```bash
[ -f ~/.claude/mailbox/mailboxd.pid ] && kill "$(cat ~/.claude/mailbox/mailboxd.pid)" 2>/dev/null; sleep 1
rm -f ~/.claude/mailbox/mailboxd.sock
~/.claude/mailbox/mailbox ps
```
Expected: `ps` works (daemon respawned from vendored bin with the `release("auto")` change in memory).

- [ ] **Step 5: Live end-to-end check of turn-end release**

Run:
```bash
~/.claude/mailbox/mailbox claims
```
Expected: returns without error. (Full behavioral proof is covered by the automated engine/hook tests; this confirms the live daemon is healthy post-restart.)

- [ ] **Step 6: Secrets/base-purity scan**

Run: `.venv/bin/python -m ccpkg scan`
Expected: exit 0, no findings.

---

## Manual smoke test (optional, end to end)

After the plan completes, to see turn-end release live: in two separate Claude Code sessions in the same directory, have session A edit a file (auto-claim), end its turn, then have session B edit the same file — B should now be allowed where previously it was denied until A's whole session ended.

---

## Self-review notes (filled by plan author)

- **Spec coverage:** Phase 0 consolidation = Tasks 0.1-0.5 (incl. the spec's "confirm vendored canonical" → fixing the red install test, re-point, daemon restart, smoke, delete-with-confirm). Phase 1 claim fix = Tasks 1-5 (release "auto" selector + Stop hook + 3-place registration + re-install/daemon-restart verification). Tests map to every acceptance criterion: release-auto-keeps-explicit (Task 1), cross-session writability (Task 2), Stop-hook + presence-active + fail-open (Task 3), protocol/CLI reuse means the existing dispatch test already covers `release` (no new protocol test needed since `release` is unchanged in OPS). ✅
- **Refinement noted:** `release(selector="auto")` reused instead of a new `release_auto` op — documented at top and in the spec's intent. Behavior + acceptance unchanged. ✅
- **Placeholder scan:** the only soft spot is Task 0.1 Step 4 (doc reconcile) and Task 3 Step 1 note about `_run_hook`'s empty-stdin form — both give concrete inspect-then-match instructions rather than guessing a helper signature I haven't pinned. Acceptable. ✅
- **Name consistency:** `release(session_id, selector, force=False)`, selector values `"all"`/`"auto"`/claim-id; hook file `stop.py`; event `"Stop"`; used consistently across Tasks 1, 3, 4. ✅
- **Ordering safety:** Phase 0 deletes the standalone only after live points at vendored; Phase 1 edits vendored then restarts the daemon so the running coordinator actually uses the new code. ✅
