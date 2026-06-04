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


def _cmd_install(root, home, env, os_name):
    report = installer.install(root, home, env, os_name)
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


def _cmd_pull(root, home, env, os_name):
    results = _apply_base_and_overlay(root, home, env, os_name, run=None)
    _print_results(results)
    return 0


def _cmd_push(root, home, env, os_name, paths):
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
    drift = _compute_drift(root, home, os_name)
    for path_rel, status in drift:
        print("{0}\t{1}".format(path_rel, status))
    print("note: run `claude doctor` for a Claude Code health report.")
    return 0


def _build_parser():
    parser = argparse.ArgumentParser(prog="ccpkg")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("install")
    sub.add_parser("pull")
    p_push = sub.add_parser("push")
    p_push.add_argument("paths", nargs="*")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("scan")
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2
    root, home, env, os_name = _resolve()
    if args.cmd == "install":
        return _cmd_install(root, home, env, os_name)
    if args.cmd == "pull":
        return _cmd_pull(root, home, env, os_name)
    if args.cmd == "push":
        return _cmd_push(root, home, env, os_name, args.paths)
    if args.cmd == "scan":
        return _cmd_scan(root, home, env, os_name)
    if args.cmd == "status" or args.cmd == "doctor":
        return _cmd_status(root, home, env, os_name)
    parser.print_help()
    return 2
