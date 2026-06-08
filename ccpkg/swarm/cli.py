"""Swarm CLI: launch / close / status / sweep."""
import argparse
import json
import os
import shutil
import sys

from . import iterm, launch, workdir


def _cmd_launch(args):
    payload = json.loads(args.payload)
    sid = launch.launch_swarm(
        task=payload["task"],
        subtasks=payload["subtasks"],
    )
    print(sid)
    return 0


def _cmd_collect(args):
    results = launch.collect(args.swarm_id)
    print(json.dumps(results, indent=2))
    return 0


def _cmd_status(args):
    swarms = workdir.list_swarms()
    if not swarms:
        print("(no active swarms)")
        return 0
    for s in swarms:
        leads = ", ".join(s.get("leads") or [])
        print(f"{s['swarm_id']}  task=\"{s.get('task','')[:50]}\"  leads=[{leads}]")
    return 0


def _cmd_close(args):
    swarms = workdir.list_swarms()
    if args.swarm_id:
        swarms = [s for s in swarms if s["swarm_id"] == args.swarm_id]
    pane_ids = []
    for s in swarms:
        pane_ids.extend((s.get("pane_ids") or {}).values())
    iterm.close_panes(pane_ids)
    return 0


def _cmd_sweep(args):
    root = workdir._root_dir()
    if not os.path.isdir(root):
        return 0
    for name in os.listdir(root):
        path = os.path.join(root, name)
        try:
            shutil.rmtree(path)
        except OSError:
            continue
    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    p = argparse.ArgumentParser(prog="ccpkg.swarm")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("launch")
    sp.add_argument("--payload", required=True,
                    help="JSON: {task, subtasks: {lead: subtask}}")
    sp = sub.add_parser("collect")
    sp.add_argument("swarm_id")
    sub.add_parser("status")
    sp = sub.add_parser("close")
    sp.add_argument("swarm_id", nargs="?")
    sub.add_parser("sweep")
    args = p.parse_args(argv)
    dispatch = {
        "launch": _cmd_launch,
        "collect": _cmd_collect,
        "status": _cmd_status,
        "close": _cmd_close,
        "sweep": _cmd_sweep,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
