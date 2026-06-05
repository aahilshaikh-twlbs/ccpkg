"""argparse CLI binding every ccpkg module (contract section 14).

`python3 -m ccpkg <install|pull|push|status|doctor|scan>`. Stdlib only, Python 3.9.
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

from . import apply
from . import config
from . import installer
from . import localenv
from . import manifest
from . import osenv
from . import plugins
from . import push
from . import scan
from . import __version__


def _resolve(argv_root=None):
    # returns (root, home, env, os_name). root/home come from config (monkeypatchable);
    # env from localenv.load(config.localenv_path(root)).
    root = config.repo_root()
    home = config.home_target()
    env = localenv.load(config.localenv_path(root))
    os_name = osenv.detect_os()
    return root, home, env, os_name


def _vault_enabled(env):
    vault_root = env.get("VAULT_ROOT", "")
    return bool(vault_root) and os.path.isdir(vault_root)


def _apply_base_and_overlay(root, home, env, os_name, run):
    # pull / shared path: apply base then overlay only. returns combined results list.
    items = manifest.parse(config.manifest_path(root))
    vars_ = localenv.template_vars(env)
    vault = _vault_enabled(env)
    src_base = config.home_claude_src(root)
    results = []
    results.extend(
        apply.apply_layer(items, "base", src_base, home, vars_, vault, os_name)
    )
    overlay_dir = installer.clone_overlay(env, run=run)
    if overlay_dir:
        overlay_manifest = os.path.join(overlay_dir, "manifest.json")
        if os.path.exists(overlay_manifest):
            ov_items = manifest.parse(overlay_manifest)
            ov_src = os.path.join(overlay_dir, "home", ".claude")
            results.extend(
                apply.apply_layer(
                    ov_items, "overlay", ov_src, home, vars_, vault, os_name
                )
            )
    return results


def _base_source_files(root):
    # all files under home/.claude (the base source-of-truth) for scan/status.
    src_base = config.home_claude_src(root)
    out = []
    for dirpath, _dirnames, filenames in os.walk(src_base):
        for name in filenames:
            out.append(os.path.join(dirpath, name))
    return out


def _compute_drift(root, home, os_name):
    # returns list of (path_rel, status): "missing" | "drift" | "ok" for each base item.
    items = manifest.parse(config.manifest_path(root))
    src_base = config.home_claude_src(root)
    drift = []
    for item in items:
        if not manifest.applies_to_os(item, os_name):
            continue
        if item.layer != "base":
            continue
        src = os.path.join(src_base, item.path)
        target = os.path.join(home, item.path)
        if not os.path.exists(target):
            drift.append((item.path, "missing"))
            continue
        if os.path.isdir(src) or os.path.islink(target):
            drift.append((item.path, "ok"))
            continue
        try:
            with open(src, "r") as fh:
                src_text = fh.read()
            with open(target, "r") as fh:
                tgt_text = fh.read()
        except OSError:
            drift.append((item.path, "drift"))
            continue
        drift.append((item.path, "ok" if src_text == tgt_text else "drift"))
    return drift


def _print_findings(findings):
    for f in findings:
        print("{0}:{1}: {2}: {3}".format(f.path, f.line, f.rule, f.detail))


def _print_results(results):
    for path_rel, result in results:
        print("{0}\t{1}".format(path_rel, result))


def _cmd_install(root, home, env, os_name, yes=False, reconfigure=False):
    from . import manifest, selectables, selection, profile, wizard

    items = manifest.parse(config.manifest_path(root))
    overlay_present = bool(
        env.get("OVERLAY_DIR") or env.get("OVERLAY_REPO")
    )
    prof = profile.load(home)
    is_tty = (not yes) and _stdin_is_tty()

    def _run_wizard(stages, preselected):
        # `existing` drives the splash status line (re-run vs fresh install).
        return wizard.run_wizard(stages, preselected, existing=prof is not None)

    try:
        selected = selection.resolve_selection(
            items, selectables.SELECTABLES, overlay_present,
            profile_obj=prof, is_tty=is_tty, reconfigure=reconfigure,
            run_wizard=_run_wizard,
        )
    except KeyboardInterrupt:
        # Clean cancel from the wizard: nothing applied, nothing persisted.
        print("install cancelled")
        return 130

    # The WIZARD owns the profile: persist whenever it actually ran, i.e. any
    # interactive (TTY) session — re-runs now always reopen the picker, so the
    # (possibly updated) selection is what we save. A headless run (--yes) or a
    # plain profile replay must NOT (re)write it.
    if is_tty:
        all_ids = selection.default_ids(
            items, selectables.SELECTABLES, overlay_present) | set(selected)
        deselected = sorted(all_ids - set(selected))
        profile.save(home, profile.Profile(selected=sorted(selected),
                                            deselected=deselected))

    report = installer.install(root, home, env, os_name, selected=set(selected))
    print("os: {0}".format(report.os))
    for pkg, status in report.deps.items():
        print("dep {0}\t{1}".format(pkg, status))
    _print_results(report.base_applied)
    _print_results(report.overlay_applied)
    for plugin, status in report.plugins.items():
        print("plugin {0}\t{1}".format(plugin, status))
    for name, status in report.mailbox.items():
        print("mailbox {0}\t{1}".format(name, status))
    _print_findings(report.scan_findings)
    for note in report.notes:
        print("note: {0}".format(note))
    return 0


def _stdin_is_tty():
    try:
        return bool(sys.stdin.isatty())
    except Exception:
        return False


def _cmd_pull(root, home, env, os_name):
    results = _apply_base_and_overlay(root, home, env, os_name, run=None)
    _print_results(results)
    return 0


def _is_git_checkout(root):
    # type: (str) -> bool
    return os.path.isdir(os.path.join(root, ".git"))


def _cmd_push(root, home, env, os_name, paths):
    if config.is_packaged() or not _is_git_checkout(root) or not os.access(root, os.W_OK):
        print(
            "ccpkg push: requires a git checkout of ccpkg; clone the repo for the "
            "dev workflow (this looks like a packaged / read-only install).",
            file=sys.stderr,
        )
        return 2
    summary = push.push(root, home, env, paths, os_name=os_name)
    for bucket in ("written", "skipped", "blocked"):
        for p in summary.get(bucket, []):
            print("{0}\t{1}".format(bucket, p))
    return 0


def _cmd_scan(root, home, env, os_name):
    # Repo-wide sweep of every shippable file (secrets + purity). See
    # scan.scan_repo for the per-file-type policy.
    terms = scan.load_purity_terms(root)
    findings = scan.scan_repo(root, terms)
    _print_findings(findings)
    if scan.is_clean(findings):
        return 0
    return 1


def _cmd_status(root, home, env, os_name):
    # status = per-file drift between the repo and the live ~/.claude.
    drift = _compute_drift(root, home, os_name)
    for path_rel, status in drift:
        print("{0}\t{1}".format(path_rel, status))
    print("note: run `ccpkg doctor` for an environment health report.")
    return 0


def _cmd_doctor(root, home, env, os_name):
    # doctor = environment health: deps, profile, mailbox, and a drift SUMMARY
    # (distinct from `status`, which lists per-file drift).
    from collections import Counter
    from . import profile

    print("ccpkg doctor")
    print("os\t{0}".format(os_name))
    for dep in ("git", "python3", "jq"):
        print("dep {0}\t{1}".format(dep, "present" if osenv.have(dep) else "MISSING"))

    prof = profile.load(home)
    if prof is None:
        print("profile\tnone (run `ccpkg install`)")
    else:
        print("profile\t{0} selected".format(len(prof.selected)))

    sock = os.path.join(home, "mailbox", "mailboxd.sock")
    mb_dir = os.path.join(home, "mailbox")
    if os.path.exists(sock):
        mb = "running"
    elif os.path.isdir(mb_dir):
        mb = "installed (daemon stopped)"
    else:
        mb = "absent"
    print("mailbox\t{0}".format(mb))

    counts = Counter(status for _p, status in _compute_drift(root, home, os_name))
    print("drift\t{0} ok · {1} drift · {2} missing".format(
        counts.get("ok", 0), counts.get("drift", 0), counts.get("missing", 0)))
    if counts.get("drift", 0) or counts.get("missing", 0):
        print("note: run `ccpkg status` for per-file detail, then `ccpkg pull` "
              "to re-apply.")
    print("note: run `claude doctor` for a Claude Code health report.")
    return 0


def _cmd_uninstall(root, home, env, os_name, yes=False):
    from . import uninstall as _uninstall

    targets = _uninstall.plan(root, home, os_name)
    if not yes:
        # Destructive + irreversible-ish. Without --yes we ONLY proceed after an
        # explicit interactive 'yes'. Non-interactive (piped/CI) without --yes
        # must REFUSE rather than run silently.
        if not _stdin_is_tty():
            print("ccpkg uninstall: refusing to run non-interactively without "
                  "--yes (this removes managed files from {0}). Re-run with "
                  "--yes to confirm.".format(home), file=sys.stderr)
            return 2
        print("ccpkg uninstall will remove these managed files from {0}:".format(home))
        for t in targets:
            print("  {0}".format(t))
        print("  …plus the mailbox runtime and the saved profile. "
              "*.ccpkg.bak backups are restored where present; settings.json is "
              "never deleted (backup restored, or left for manual review).")
        try:
            resp = input("Proceed? [y/N] ").strip().lower()
        except EOFError:
            resp = ""
        if resp not in ("y", "yes"):
            print("uninstall cancelled")
            return 130
    results = _uninstall.uninstall(root, home, os_name)
    for label, status in results:
        print("{0}\t{1}".format(label, status))
    return 0


def _build_parser():
    parser = argparse.ArgumentParser(prog="ccpkg")
    parser.add_argument(
        "--version", action="version", version="ccpkg " + __version__
    )
    sub = parser.add_subparsers(dest="cmd")
    p_install = sub.add_parser("install")
    p_install.add_argument("--yes", "--non-interactive", dest="yes",
                           action="store_true",
                           help="headless: apply profile or defaults, no prompts")
    p_install.add_argument("--reconfigure", dest="reconfigure",
                           action="store_true",
                           help="re-run the interactive wizard even if a profile exists")
    sub.add_parser("pull")
    p_push = sub.add_parser("push")
    p_push.add_argument("paths", nargs="*")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("scan")
    p_uninstall = sub.add_parser("uninstall")
    p_uninstall.add_argument("--yes", "--non-interactive", dest="yes",
                             action="store_true",
                             help="skip the confirmation prompt")
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2
    root, home, env, os_name = _resolve()
    if args.cmd == "install":
        return _cmd_install(root, home, env, os_name,
                            yes=getattr(args, "yes", False),
                            reconfigure=getattr(args, "reconfigure", False))
    if args.cmd == "pull":
        return _cmd_pull(root, home, env, os_name)
    if args.cmd == "push":
        return _cmd_push(root, home, env, os_name, args.paths)
    if args.cmd == "scan":
        return _cmd_scan(root, home, env, os_name)
    if args.cmd == "status":
        return _cmd_status(root, home, env, os_name)
    if args.cmd == "doctor":
        return _cmd_doctor(root, home, env, os_name)
    if args.cmd == "uninstall":
        return _cmd_uninstall(root, home, env, os_name,
                              yes=getattr(args, "yes", False))
    parser.print_help()
    return 2
