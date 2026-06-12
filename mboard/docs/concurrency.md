# Mboard — write concurrency model

**Status:** Implemented (describes current behavior)
**Scope:** How concurrent writes to a board are serialized. Answers: *can two
agents writing the board at the same time race or deadlock?* (No.)

## TL;DR

Every board mutation runs **inside one daemon process**, **serialized by a single
in-process mutex**, and **persisted atomically**. Clients never write board files
directly. There is therefore **no write race and no deadlock**, and you do **not**
need to add any per-client lock or semaphore on top — the mutex already exists and
adding more would be redundant (and risks introducing the contention you're avoiding).

## Architecture: one daemon, many clients

The mboard is a single long-lived **daemon** (`mboard.daemon`) listening on a Unix
domain socket (`~/.claude/mboard/mboardd.sock`). Every participant — an agent, a
standalone session, or a team lead — is just a **client** of that one daemon:

- `client.py` is **socket-only**: `_connect()` opens an `AF_UNIX` stream to
  `config.socket_path()`; `request(op, args, autospawn=True)` sends one
  newline-delimited JSON request and reads one response. If no daemon is reachable it
  **autospawns** one (`python -m mboard.daemon`) and waits for it to come up — it does
  **not** fall back to writing state itself.
- The only code that writes board state is `engine.py` (and `daemon.py` for its
  pidfile), and that code runs **only inside the daemon**.

Because there is exactly one daemon per host, this same mechanism covers **both**
intra-team coordination **and** cross-session coordination: independent sessions are
not blind to each other, they are all clients of the same serializing process.

## The single-writer invariant (the "semaphore")

The daemon's request handler wraps **every** dispatch in one process-wide lock:

```python
# server.py — _MboardStreamHandler.handle
with self.server.engine_lock:            # threading.Lock(), created in MboardServer.__init__
    response = protocol.dispatch(self.server.engine, request)
```

The server uses `ThreadingMixIn`, so each *connection* is handled on its own thread —
but the actual state mutation (`protocol.dispatch` → `engine` method) only runs while
holding `engine_lock`. So **at most one request mutates board state at any instant.**
That lock *is* the "writer holds a semaphore for that moment" model — implemented once,
centrally, instead of once per client.

### Why this is race-free
All mutations are totally ordered by `engine_lock`. Two clients that send overlapping
writes are serviced one-after-the-other; neither sees a partially-applied state.

### Why this is deadlock-free
`engine_lock` is a **single, non-reentrant lock**, acquired once per request and
released when the handler returns. There is no second lock to order it against, no
nested acquisition, and the critical section does only local CPU + disk work (it never
blocks waiting on another client). A single lock with no nesting cannot deadlock.

## Crash-safe persistence

State is written with `store.atomic_write_json`, which never leaves a torn file:

```python
# store.py — atomic_write_json
fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=dir_path)  # same dir
... json.dump(obj, f); f.flush(); os.fsync(f.fileno()) ...
os.replace(tmp_path, path)   # atomic rename on POSIX
```

Write-to-temp + `fsync` + `os.replace` means a reader either sees the complete old file
or the complete new one — never a half-written board — and a crash mid-write cannot
corrupt existing state (the orphaned `.tmp-*` file is ignored/swept on read).

## Do NOT add a per-client file lock

A tempting "fix" is to have each writer `flock` the board file before writing. Don't:
clients don't write the file at all (only the daemon does), and layering advisory file
locks on top of the daemon mutex adds nothing while reintroducing the classic failure
modes the daemon design avoids (stale locks from crashed holders, lock-ordering
deadlocks across files, cross-host NFS lock unreliability). The centralized
single-writer daemon is the stronger guarantee.

## Out of scope: claim *lifecycle* ≠ write concurrency

This document is about **write serialization**, which is solved. A separate concern is
the **lifecycle** of claims/presence — when a claim is released. Claims are released on
session end (via the `session_end` hook) and by the engine's GC pass, not by the write
lock. If claims appear to "pile up" and self-block a long multi-phase run, that is a
lifecycle/GC matter, **not** a write race — look at the session-end hook and GC, not at
locking.

## Source map

| Concern | File / symbol |
|---|---|
| Client transport (socket-only, autospawn) | `src/mboard/client.py` — `_connect`, `request` |
| Request loop + the single-writer lock | `src/mboard/server.py` — `_MboardStreamHandler.handle`, `MboardServer.engine_lock` |
| Mutations (only writer of board state) | `src/mboard/engine.py` → `store.atomic_write_json` |
| Atomic persistence | `src/mboard/store.py` — `atomic_write_json` |
| Daemon entrypoint / pidfile | `src/mboard/daemon.py` |
