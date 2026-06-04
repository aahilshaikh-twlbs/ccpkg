import argparse
import os
import sys
from typing import List, Optional

from . import client


def _resolve_session(args) -> Optional[str]:
    if getattr(args, "session", None):
        return args.session
    env = os.environ.get("MAILBOX_SESSION_ID")
    if env:
        return env
    return None


def _abspath(p: str) -> str:
    return os.path.abspath(p)


def _print_inbox(messages: list) -> None:
    if not messages:
        print("(no messages)")
        return
    for m in messages:
        print("[%s] from %s: %s" % (
            m.get("kind", "note"),
            m.get("from_label", "?"),
            m.get("body", ""),
        ))


def _print_claims(claims: list) -> None:
    if not claims:
        print("(no claims)")
        return
    for c in claims:
        print("%s  %-8s  %-7s  %s%s" % (
            c.get("id", "?"),
            c.get("holder_status", "?"),
            c.get("kind", "?"),
            ",".join(c.get("paths", [])),
            ("  # " + c["note"]) if c.get("note") else "",
        ))


def _print_ps(rows: list) -> None:
    if not rows:
        print("(nobody here)")
        return
    for r in rows:
        print("%-20s  %-7s  %ss ago  %s" % (
            r.get("label", "?"),
            r.get("status", "?"),
            int(r.get("last_seen_seconds", 0)),
            r.get("cwd", ""),
        ))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mailbox")
    p.add_argument("--session", default=None)
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("join")
    sp.add_argument("--board", default=None)
    sp.add_argument("--label", default=None)

    sp = sub.add_parser("claim")
    sp.add_argument("globs", nargs="+")
    sp.add_argument("--note", default=None)

    sp = sub.add_parser("release")
    sp.add_argument("selector")
    sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("seize")
    sp.add_argument("path")

    sp = sub.add_parser("request-release")
    sp.add_argument("path")

    sp = sub.add_parser("send")
    sp.add_argument("body")
    sp.add_argument("--to", default="*")
    sp.add_argument("--kind", default="note")

    sub.add_parser("inbox")

    sp = sub.add_parser("claims")
    sp.add_argument("--mine", action="store_true")
    sp.add_argument("--all", action="store_true")

    sub.add_parser("ps")
    sub.add_parser("board")
    sub.add_parser("whoami")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "cmd", None):
        parser.print_help(sys.stderr)
        return 1

    session_id = _resolve_session(args)
    if not session_id:
        print("no session id (run inside a Claude session)", file=sys.stderr)
        return 1

    cmd = args.cmd

    if cmd == "join":
        op = "join"
        op_args = {
            "session_id": session_id,
            "label": args.label or session_id,
            "cwd": os.getcwd(),
            "board_name": args.board,
        }
    elif cmd == "claim":
        op = "claim"
        op_args = {
            "session_id": session_id,
            "globs": [_abspath(g) for g in args.globs],
            "note": args.note,
        }
    elif cmd == "release":
        op = "release"
        op_args = {
            "session_id": session_id,
            "selector": args.selector,
            "force": args.force,
        }
    elif cmd == "seize":
        op = "seize"
        op_args = {
            "session_id": session_id,
            "abs_path": _abspath(args.path),
        }
    elif cmd == "request-release":
        op = "request_release"
        op_args = {
            "session_id": session_id,
            "abs_path": _abspath(args.path),
        }
    elif cmd == "send":
        op = "send"
        op_args = {
            "session_id": session_id,
            "to": args.to,
            "kind": args.kind,
            "body": args.body,
        }
    elif cmd == "inbox":
        op = "poll_inbox"
        op_args = {"session_id": session_id}
    elif cmd == "claims":
        if args.all:
            scope = "all"
        elif args.mine:
            scope = "mine"
        else:
            scope = "board"
        op = "list_claims"
        op_args = {"session_id": session_id, "scope": scope}
    elif cmd == "ps":
        op = "ps"
        op_args = {"session_id": session_id}
    elif cmd == "board":
        op = "board"
        op_args = {"session_id": session_id}
    elif cmd == "whoami":
        op = "whoami"
        op_args = {"session_id": session_id}
    else:
        print("unknown command: %s" % cmd, file=sys.stderr)
        return 1

    resp = client.request(op, op_args)

    if not resp.get("ok"):
        print(resp.get("error", "error"), file=sys.stderr)
        return 1

    data = resp.get("data")
    if cmd == "inbox":
        _print_inbox(data or [])
    elif cmd == "claims":
        _print_claims(data or [])
    elif cmd == "ps":
        _print_ps(data or [])
    else:
        print(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
