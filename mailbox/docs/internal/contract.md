# Mailbox — Frozen Implementation Contract

This is the **single source of truth** for the implementation plan. Every task binds
to the exact symbols, signatures, fields, and behaviors here. Do not invent names or
signatures not listed here. If something is missing, it is out of scope for v1.

Target: **Python 3.9.6** (no `match` statements, no `X | Y` runtime type unions; use
`typing.Optional`, `typing.List`, `typing.Dict`). Tests: **pytest** in a repo venv.

---

## 0. Confirmed Claude Code hook facts (from recon — authoritative)

- Events used: `SessionStart`, `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `SessionEnd`.
- Hook **stdin** is JSON with at least: `session_id`, `cwd`, `transcript_path`,
  `hook_event_name`, `permission_mode`. Plus per event:
  - SessionStart: `source` (startup|resume|clear|compact), `model`.
  - PreToolUse/PostToolUse: `tool_name`, `tool_input` (object; for Edit/Write/MultiEdit
    `tool_input.file_path`; for NotebookEdit `tool_input.notebook_path`).
  - PostToolUse also: `tool_output`. UserPromptSubmit: `prompt`. SessionEnd: payload
    **undocumented** — assume `session_id`/`cwd` present, do not rely on more.
- **PreToolUse stdout control** (exit 0 + JSON):
  ```json
  {"hookSpecificOutput":{"hookEventName":"PreToolUse",
    "permissionDecision":"allow|deny|ask|defer",
    "permissionDecisionReason":"text"},
   "additionalContext":"text injected to model"}
  ```
  - DENY: `permissionDecision:"deny"` + reason. ALLOW silently: print nothing, exit 0
    (defer to normal flow). WARN: `permissionDecision:"allow"` + `additionalContext`.
- `additionalContext` is supported on SessionStart, PreToolUse, PostToolUse,
  UserPromptSubmit. Top-level `systemMessage` shown to user on any event.
- SessionStart: plain stdout (exit 0) is also added to context (no JSON wrapper needed).
- Exit code 2 = blocking error (stderr shown). We prefer JSON control over exit 2.
- **Env vars:** `CLAUDE_PROJECT_DIR` available to hooks + Bash subprocesses.
  `CLAUDE_SESSION_ID` does **NOT** exist. `CLAUDE_ENV_FILE` available to SessionStart
  hooks: appending `export FOO=bar` lines persists env to later Bash subprocesses.
- `matcher` is a string; `"Edit|Write|MultiEdit|NotebookEdit"` = OR list.
- SessionEnd does not reliably fire on crash → cleanup is best-effort; GC is authority.

---

## 1. Package & file layout

```
~/Documents/Code/mailbox/            # dev repo (git)
  pyproject.toml
  .venv/                             # created by scaffold task (gitignored)
  src/mailbox/
    __init__.py
    config.py
    store.py
    models.py
    boards.py
    matching.py
    engine.py
    protocol.py
    server.py
    daemon.py
    client.py
    cli.py
  bin/mailbox                        # shell shim -> python -m mailbox.cli
  hooks/
    session_start.py
    pre_tool_use.py
    post_tool_use.py
    user_prompt_submit.py
    session_end.py
  install.py                         # idempotent installer (symlinks + settings merge)
  tests/
    conftest.py
    test_store.py
    test_models.py
    test_boards.py
    test_matching.py
    test_engine_presence.py
    test_engine_checkwrite.py
    test_engine_claims.py
    test_engine_messaging.py
    test_engine_gc.py
    test_protocol.py
    test_server.py
    test_daemon.py
    test_client.py
    test_cli.py
    test_hooks.py
    test_e2e.py
  docs/specs/2026-06-03-mailbox-design.md
  docs/internal/contract.md          # this file
```

Runtime/install target: `~/.claude/mailbox/` (symlinks to repo `src`/`bin`/`hooks`,
plus runtime `state/`, `mailboxd.sock`, `mailboxd.pid`, `mailboxd.log`).

---

## 2. config.py — constants & path resolution

```python
import os

def home() -> str:
    return os.environ.get("MAILBOX_HOME", os.path.expanduser("~/.claude/mailbox"))

def state_dir() -> str:   return os.path.join(home(), "state")
def socket_path() -> str: return os.environ.get("MAILBOX_SOCKET", os.path.join(home(), "mailboxd.sock"))
def pidfile() -> str:     return os.path.join(home(), "mailboxd.pid")
def logfile() -> str:     return os.path.join(home(), "mailboxd.log")

HEARTBEAT_STALE_SECONDS = 90        # presence stale after this with no heartbeat
AUTO_CLAIM_TTL_SECONDS = 300        # auto-claim expiry (refreshed by heartbeat)
EXPLICIT_CLAIM_TTL_SECONDS = 86400  # explicit claim expiry (24h)
OFFLINE_GRACE_SECONDS = 180         # mark live->offline after 2x stale w/o heartbeat
MESSAGE_RETENTION_SECONDS = 3600    # GC read messages older than this
PRESENCE_RETENTION_SECONDS = 86400  # GC offline presence older than this
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SOCKET_TIMEOUT_SECONDS = 5
SPAWN_WAIT_SECONDS = 5
```

All functions take `state_dir`/`socket_path` so tests can inject temp dirs via env
(`MAILBOX_HOME`, `MAILBOX_SOCKET`).

---

## 3. models.py — dataclasses

Use `@dataclass`; each has `to_dict()` returning a plain dict and a classmethod
`from_dict(d)` that tolerates missing optional keys.

```python
@dataclass
class Presence:
    session_id: str
    label: str
    cwd: str
    boards: List[str]          # boards[0] = repo board; boards[1:] = named boards
    joined: float
    last_heartbeat: float
    status: str                # "active" | "offline"
    team: Optional[str] = None
    member: Optional[str] = None

@dataclass
class Claim:
    id: str                    # "clm_" + 12 hex
    board: str
    session_id: str
    label: str
    paths: List[str]           # ABSOLUTE path globs (may contain ** and *)
    kind: str                  # "auto" | "explicit"
    created: float
    expires: float
    released: bool = False
    note: Optional[str] = None

@dataclass
class Message:
    id: str                    # "msg_" + 12 hex
    board: str
    from_session: str
    from_label: str
    to: str                    # session_id | label | "*"
    kind: str                  # "note"|"release-request"|"dep-signal"|"handoff"|"done"
    body: str
    created: float
    read_by: List[str] = field(default_factory=list)
    ref_paths: List[str] = field(default_factory=list)
```

ID generation lives in engine (`_gen_id(prefix)` → `prefix + uuid4().hex[:12]`).

---

## 4. store.py — atomic JSON persistence (pure, no engine knowledge)

```python
def atomic_write_json(path: str, obj: dict) -> None
    # mkdir -p dirname; write to NamedTemporaryFile in same dir; os.replace(tmp, path)

def read_json(path: str) -> Optional[dict]
    # return parsed dict; return None if missing OR malformed (never raise)

def iter_json(dir_path: str) -> Iterator[Tuple[str, dict]]
    # yield (filepath, parsed) for every *.json in dir_path, skipping malformed;
    # if dir missing, yield nothing

def remove(path: str) -> None
    # unlink if exists; never raise on missing
```

---

## 5. boards.py — board id derivation

```python
def derive_repo_board(cwd: str) -> Tuple[str, str]
    # Try: git -C <cwd> rev-parse --show-toplevel  (subprocess, 2s timeout)
    # success -> ("repo-" + sha1(toplevel).hexdigest()[:12], toplevel)
    # failure (not a repo / git missing) -> ("cwd-" + sha1(cwd).hexdigest()[:12], cwd)
    # NOTE: working-tree root, NOT --git-common-dir, so worktrees are distinct boards.

def board_id_for_name(name: str) -> str
    # "named-" + re.sub(r'[^a-z0-9]+','-', name.lower()).strip('-')[:40]
```

---

## 6. matching.py — glob path matching

```python
def path_matches(glob: str, abs_path: str) -> bool
    # Match an absolute glob against an absolute path. Support:
    #   *   -> any chars except "/"
    #   **  -> any chars including "/" (recursive)
    #   ?   -> single non-"/" char
    # Exact (non-glob) string matches itself. Implement by translating glob to a
    # regex anchored with ^...$ . A bare directory glob "X/sub" must also match files
    # under it: treat a glob with no wildcard that is a prefix dir of abs_path as a
    # match (i.e. claiming "/a/b" covers "/a/b/c.py"). Globs containing wildcards use
    # pure regex translation.
```

Conflict detection is done in engine using `path_matches`; matching.py has no engine deps.

---

## 7. engine.py — MailboxEngine (the core; pure, clock-injected)

State (all in-memory, mirrored to `state_dir/boards/<board>/{presence,claims,messages}`):
```python
class MailboxEngine:
    def __init__(self, state_dir: str, now_fn=time.time):
        self.state_dir = state_dir
        self.now = now_fn
        self.boards: Dict[str, dict] = {}        # board_id -> meta dict
        self.presence: Dict[str, Presence] = {}  # session_id -> Presence
        self.claims: Dict[str, Claim] = {}       # claim_id -> Claim
        self.messages: Dict[str, Message] = {}   # msg_id -> Message
        self.load()
```

### Helpers (define in the presence task; later tasks assume they exist)
```python
def _now(self) -> float                          # self.now()
def _gen_id(self, prefix: str) -> str            # prefix + uuid4().hex[:12]
def _is_live(self, p: Presence) -> bool          # p.status=="active" and now-p.last_heartbeat <= HEARTBEAT_STALE_SECONDS
def _ensure_board(self, board_id, origin, name=None) -> None   # create+persist meta if absent
def _board_dir(self, board_id) -> str            # state_dir/boards/<board_id>
def _persist_presence(self, p) / _persist_claim(self, c) / _persist_message(self, m)
def _repo_board(self, session_id) -> str         # presence[session].boards[0]
def _primary_board(self, session_id) -> str      # boards[-1] (named if joined, else repo)
def load(self) -> None                           # read all boards/*/{presence,claims,messages}/*.json into memory
```

### Method signatures & semantics (return plain dicts/lists, JSON-serializable)

```python
def join(self, session_id, label, cwd, team=None, member=None, board_name=None) -> dict
    # derive repo board; ensure; boards=[repo]; if board_name: append named board.
    # upsert presence (active, heartbeat=now; preserve joined if existing).
    # If presence newly created OR was offline, broadcast a co-location note to each
    # board that already has >=1 OTHER live member (kind="note", to="*", from this
    # session, body "<label> joined <checkout|board> — N now active; coordinate via mailbox").
    # return {"boards":[...], "colocated": {board_id:[labels]}, "label": label}

def heartbeat(self, session_id) -> dict
    # if no presence -> {"ok": False, "need_join": True}
    # else refresh last_heartbeat=now; if status offline set active; extend expires of
    # this session's live auto-claims to now+AUTO_CLAIM_TTL_SECONDS. return {"ok": True}

def leave(self, session_id) -> dict
    # mark presence offline; release (released=True) ALL of this session's claims
    # (auto + explicit) — clean exit drops territory. return {"ok": True}

def check_write(self, session_id, abs_path) -> dict
    # presence must exist; if not -> {"decision":"allow","reason":"no-presence"} (fail open)
    # boards = set(presence.boards)
    # conflicts = [c for c in claims.values() if not c.released and c.session_id != session_id
    #              and c.board in boards and any(path_matches(g, abs_path) for g in c.paths)]
    # live = [c for c in conflicts if presence.get(c.session_id) and _is_live(that presence)]
    # if live: pick first -> {"decision":"deny","holder":label,"holder_session":sid,
    #            "note":c.note,"since_seconds":now-hb,"claim_id":c.id}
    # elif conflicts (all stale): pick first -> {"decision":"warn","holder":label,
    #            "note":c.note,"stale_seconds":now-hb,"claim_id":c.id}
    # else (no conflict): upsert this session's auto-claim on repo board boards[0]:
    #            one auto claim per (session, repo_board); append abs_path to its paths
    #            (dedup); expires=now+AUTO_CLAIM_TTL; create if absent. persist.
    #            -> {"decision":"allow","claim_id":auto.id}

def claim(self, session_id, globs, note=None, kind="explicit") -> dict
    # globs are ABSOLUTE (CLI/hook normalize). board = repo board (boards[0]).
    # expires = now + (EXPLICIT_CLAIM_TTL if kind=="explicit" else AUTO_CLAIM_TTL).
    # create Claim, persist. return claim.to_dict()

def release(self, session_id, selector, force=False) -> dict
    # selector: "all" | a claim id | a glob string.
    # "all": release all of session's claims. claim-id: release that claim (only if
    # owned by session unless force=True). glob: release session's claims whose paths
    # contain that exact glob. return {"released":[ids]}

def seize(self, session_id, abs_path) -> dict
    # conflicts = others' unreleased claims matching abs_path.
    # if any holder is live -> {"error":"holder-live","holder":label}
    # else release those stale claims; create explicit claim for seizer on abs_path
    # note="seized". return {"seized":[ids],"claim":claim.to_dict()}

def request_release(self, session_id, abs_path) -> dict
    # find another session's unreleased claim matching abs_path; if none ->
    # {"error":"no-holder"}. else send(kind="release-request", to=holder.label,
    # body "Please release <abs_path>", ref_paths=[abs_path]). return {"sent_to":label}

def send(self, session_id, to, kind, body, ref_paths=None) -> dict
    # board = _primary_board(session). create Message(from this session), persist.
    # return {"id": msg_id}

def poll_inbox(self, session_id) -> list
    # boards = set(presence.boards). return (and mark read) messages where
    # m.board in boards and m.from_session != session_id and session_id not in m.read_by
    # and (m.to=="*" or m.to==session_id or m.to==presence.label). sort by created asc.
    # each item = m.to_dict(). Marking read appends session_id to read_by + persists.

def list_claims(self, session_id, scope="board") -> list
    # scope "board": all unreleased claims on session's boards; "mine": only session's;
    # "all": every unreleased claim. Each dict = claim.to_dict() + {"live": bool,
    # "holder_status": "active"|"stale"|"offline"}.

def ps(self, session_id) -> list
    # presences sharing >=1 board with session. each = {"session_id","label","cwd",
    # "member","status": "active"|"stale"|"offline","last_seen_seconds","boards"}.

def whoami(self, session_id) -> dict        # presence.to_dict() + {"exists": bool}
def board(self, session_id) -> dict         # {"boards":[{"id","origin","name","members":N,"claims":N}]}

def gc(self) -> dict
    # 1) live presence with now-last_heartbeat > OFFLINE_GRACE -> status offline +
    #    release its auto claims.
    # 2) claims: released+old(> MESSAGE_RETENTION) -> delete file+dict; auto expired
    #    (now>expires) -> released=True; holder offline -> released=True.
    # 3) messages older than MESSAGE_RETENTION -> delete.
    # 4) offline presence older than PRESENCE_RETENTION -> delete.
    # return {"presence_offlined":n,"claims_reaped":n,"messages_gc":n}
```

---

## 8. protocol.py — framing + dispatch

```python
def encode(obj: dict) -> bytes          # json.dumps(obj).encode()+b"\n"
def decode(line: bytes) -> dict         # json.loads(line)

OPS = {  # op name -> engine method name (1:1)
  "join","heartbeat","leave","check_write","claim","release","seize",
  "request_release","send","poll_inbox","list_claims","ps","whoami","board","gc","ping"
}

def dispatch(engine, request: dict) -> dict
    # op = request["op"]; args = request.get("args", {})
    # "ping" -> {"ok": True, "data": "pong"}
    # unknown op -> {"ok": False, "error": "unknown op: <op>"}
    # else: data = getattr(engine, op)(**args); return {"ok": True, "data": data}
    # any exception -> {"ok": False, "error": "<ExcType>: <msg>"}  (never raise)
```

Request shape on the wire: `{"op": "...", "args": {...}}`. Response:
`{"ok": bool, "data": ..., "error": ...}`.

---

## 9. server.py — Unix socket server

```python
class MailboxServer:
    def __init__(self, engine, socket_path):
        # uses threading lock around dispatch (single-writer invariant)
    def serve_forever(self): ...
    def shutdown(self): ...
```
- Implement with `socketserver.ThreadingMixIn` + `socketserver.UnixStreamServer`
  (subclass `UnixStreamServer` to allow address reuse / unlink stale socket on start).
- Handler: read until newline, `protocol.decode`, acquire `engine_lock`,
  `protocol.dispatch(engine, req)`, write `protocol.encode(resp)`, close.
- On start: if `socket_path` exists, unlink it. `os.chmod(socket_path, 0o600)`.

---

## 10. daemon.py — lifecycle

```python
def write_pidfile() -> None      # {"pid","startedAt"(ms int),"procStart"(str),
                                 #  "socketPath","logPath","statePath","origin":"transient"}
def read_pidfile() -> Optional[dict]
def pid_alive(pid: int) -> bool  # os.kill(pid, 0)
def already_running() -> bool    # pidfile exists and pid_alive
def main() -> int
    # if already_running(): print to log, return 0.
    # ensure home()/state dirs. open logfile (append). build engine(state_dir()).
    # engine.load(). create MailboxServer(engine, socket_path()). write_pidfile().
    # install SIGTERM/SIGINT -> server.shutdown()+cleanup(remove socket+pidfile)+exit.
    # serve_forever().
# `python -m mailbox.daemon` calls main().
```

---

## 11. client.py — connect + autospawn

```python
def _connect(timeout=SOCKET_TIMEOUT_SECONDS) -> socket  # AF_UNIX to socket_path()
def ensure_running() -> None
    # if _connect ok (ping), close+return. else spawn detached:
    #   subprocess.Popen([sys.executable,"-m","mailbox.daemon"], stdout/stderr->logfile,
    #     stdin=DEVNULL, start_new_session=True, cwd=repo or home)
    # then poll up to SPAWN_WAIT_SECONDS for connectable socket; raise on timeout.
def request(op, args=None, session=None, autospawn=True) -> dict
    # connect; on FileNotFoundError/ConnectionRefusedError and autospawn:
    #   ensure_running(); reconnect. send encode({"op":op,"args":args or {}}); read line;
    #   return decode. On any failure return {"ok": False, "error": "..."} (never raise).
```
Note: `session` is passed inside `args` by callers (e.g. args={"session_id": sid, ...}).
The engine methods all take `session_id` as first arg → callers put it in args.

---

## 12. cli.py — `mailbox <subcommand>`

`python -m mailbox.cli`. Resolve session id: `--session` flag, else
`$MAILBOX_SESSION_ID`, else print error "no session id (run inside a Claude session)".
Resolve cwd via `os.getcwd()`. Normalize claim/seize globs+paths to absolute via
`os.path.abspath` before sending.

Subcommands → engine op (args always include resolved `session_id`):
- `join [--board NAME] [--label L]` → join
- `claim GLOB [GLOB...] [--note N]` → claim (globs abspath'd)
- `release (all|CLAIM_ID|GLOB) [--force]` → release
- `seize PATH` → seize (abspath)
- `request-release PATH` → request_release (abspath)
- `send (--to LABEL|*) [--kind KIND] BODY` → send
- `inbox` → poll_inbox (human-print each message)
- `claims [--mine|--all]` → list_claims (human table)
- `ps` → ps (human table: label, status, cwd, last seen)
- `board` → board
- `whoami` → whoami
Exit 0 on ok, 1 on `{"ok":False}` (print error to stderr).

---

## 13. hooks/*.py — thin clients (fail-open ALWAYS)

Every hook: read JSON from stdin; on ANY exception, exit 0 silently (never block work).
Import path: hooks add repo `src` to `sys.path` (or rely on installed package). Use
`from mailbox import client, config`.

- **session_start.py**: read `session_id, cwd, source`. `board_name = os.environ.get("MAILBOX_BOARD")`. `label = os.environ.get("MAILBOX_LABEL") or basename(cwd)+"-"+sid[:4]`. call `client.request("join", {"session_id":sid,"label":label,"cwd":cwd,"board_name":board_name})`. If `$CLAUDE_ENV_FILE` set: append `export MAILBOX_SESSION_ID=<sid>\n` and `export MAILBOX_LABEL=<label>\n`. If response data has non-empty `colocated`: print a plain-text line (SessionStart stdout → context): "🤝 Sharing <board> with: <labels>. File claims are auto-enforced; use `mailbox ps|claims|send|inbox` to coordinate." exit 0.

- **pre_tool_use.py**: read `session_id, cwd, tool_name, tool_input`. If `tool_name` not in `WRITE_TOOLS` → exit 0. `fp = tool_input.get("file_path") or tool_input.get("notebook_path")`; if missing → exit 0. `abs_path = os.path.abspath(os.path.join(cwd, fp))`. call `check_write`. data.decision:
  - "deny": print JSON `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"🔒 <holder> holds <abs_path> (active <since>s ago)<; note>. Coordinate: `mailbox request-release <abs_path>` or work elsewhere."}}`; exit 0.
  - "warn": print JSON `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","additionalContext":"⚠️ <holder> has a STALE claim on <abs_path> (<stale>s). Proceeding, but if they're still working this will collide. `mailbox seize <abs_path>` to take ownership."}}`; exit 0.
  - "allow"/else: exit 0 (no output; auto-claim already recorded by daemon).

- **post_tool_use.py**: read `session_id`. call `heartbeat`; call `poll_inbox`. If messages: build text "📬 Mailbox: " + one line per msg ("[kind] from <from_label>: <body>"). print JSON `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"<text>"}}`. exit 0.

- **user_prompt_submit.py**: identical to post_tool_use but `hookEventName":"UserPromptSubmit"`.

- **session_end.py**: read `session_id`. call `leave`. exit 0.

---

## 14. install.py — idempotent installer

```python
def main():
    # 1) mkdir ~/.claude/mailbox; symlink repo src->{home}/mailbox_pkg? Simpler:
    #    write {home}/mailbox (the bin shim) and ensure PYTHONPATH includes repo src.
    #    Concretely: symlink repo bin/mailbox -> {home}/mailbox; symlink hooks dir.
    # 2) Read ~/.claude/settings.json; merge mailbox hook entries WITHOUT removing the
    #    existing SUPERSET notify hooks (append into each event's array). Idempotent:
    #    skip if a hook command already contains "mailbox/hooks". Write back atomically.
    # 3) Print what changed.
```
Hook commands wired (use absolute python + hook paths):
- SessionStart: `python3 {home}/hooks/session_start.py`
- PreToolUse matcher `Edit|Write|MultiEdit|NotebookEdit`: `python3 {home}/hooks/pre_tool_use.py`
- PostToolUse matcher `*`: `python3 {home}/hooks/post_tool_use.py`
- UserPromptSubmit: `python3 {home}/hooks/user_prompt_submit.py`
- SessionEnd: `python3 {home}/hooks/session_end.py`

---

## 15. /handoff extension

Edit `~/.claude/commands/handoff.md`: add a "Mailbox coordination (multi-session)"
section. When the user hands a task to N sessions, the skill:
- Picks a board slug `handoff-<YYYY-MM-DD>-<topic-slug>`, records it in §0 Orientation.
- For each segment, lists **bootstrap commands** the receiving session runs first:
  `export MAILBOX_BOARD=<slug>` (so SessionStart joins it), then
  `mailbox claim <suggested globs> --note "<segment>"` to stake territory, and a note
  to use `mailbox ps|inbox|send` for dependency coordination.
- Each segment's "Files & locations" doubles as its claim scope (non-overlapping).
We do NOT pre-create owner-less claims; each session claims on bootstrap.

---

## 16. Test conventions (conftest.py)

- Fixture `engine` → `MailboxEngine(tmp_path, now_fn=clock)` with a mutable fake clock
  (`clock.t` advanced in tests) for deterministic liveness.
- Fixture `tmp_home(monkeypatch, tmp_path)` → sets `MAILBOX_HOME` + `MAILBOX_SOCKET`
  to tmp paths for server/daemon/client/cli/hook tests.
- Integration tests spawn the daemon via `client.ensure_running()` against the temp
  socket and assert real socket round-trips.

---

## 17. TASK LIST (authoritative order; one plan task each)

0. Scaffold: dirs, venv+pytest, `pyproject.toml`, `config.py`, `conftest.py`, `.gitignore`.
1. store.py (atomic_write_json, read_json, iter_json, remove) + test_store.
2. models.py (Presence/Claim/Message + to_dict/from_dict) + test_models.
3. boards.py (derive_repo_board, board_id_for_name) + test_boards.
4. matching.py (path_matches) + test_matching.
5. engine: ctor+load+helpers+join/heartbeat/leave + test_engine_presence.
6. engine: check_write + auto-claim + test_engine_checkwrite.
7. engine: claim/release/seize/list_claims + test_engine_claims.
8. engine: send/poll_inbox/request_release + co-location broadcast + test_engine_messaging.
9. engine: gc/ps/whoami/board + test_engine_gc.
10. protocol.py (encode/decode/dispatch) + test_protocol.
11. server.py (MailboxServer) + test_server (round-trip over temp socket).
12. daemon.py (pidfile/main/signals) + test_daemon (spawn + ping + shutdown).
13. client.py (request/ensure_running/autospawn) + test_client.
14. cli.py (argparse + output) + test_cli.
15. bin/mailbox shim (+ executable bit) + smoke test.
16. hooks/session_start.py + test_hooks (session_start path).
17. hooks/pre_tool_use.py + test_hooks (deny/warn/allow).
18. hooks/post_tool_use.py + user_prompt_submit.py + test_hooks (inbox injection).
19. hooks/session_end.py + test_hooks (leave).
20. install.py (symlinks + settings merge, idempotent) + test_install.
21. /handoff extension (edit handoff.md) — doc task, no code test.
22. test_e2e.py: 2 simulated sessions → deny-on-live, warn-on-stale, seize, message
    delivery + read receipts, co-location notice, leave releases, gc reaps.
```
