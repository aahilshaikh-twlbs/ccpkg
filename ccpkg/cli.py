"""argparse CLI binding every ccpkg module (contract section 14).

`python3 -m ccpkg <apply|status|new|push|uninstall>`. Stdlib only, Python 3.9.
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


def _all_ids(items, sels, overlay_present):
    # every selectable id the picker would surface (files + plugins + mboard).
    from . import selection
    out = set()
    for stage in selection.build_stages(items, sels, overlay_present):
        for e in stage.entries:
            out.add(e.id)
    return out


def _preset_ids(items, sels, overlay_present, preset):
    # Map a headless --preset name to a concrete id-set, mirroring the wizard's
    # preset semantics: everything=all surfaced ids, recommended=default-on,
    # minimal=required-only.
    from . import selection
    if preset == "everything":
        return _all_ids(items, sels, overlay_present)
    if preset == "minimal":
        out = set()
        for stage in selection.build_stages(items, sels, overlay_present):
            for e in stage.entries:
                if getattr(e, "required", False):
                    out.add(e.id)
        return out
    # "recommended" (and any unknown value) -> the default-on set.
    return selection.default_ids(items, sels, overlay_present)


def _cmd_install(root, home, env, os_name, yes=False, reconfigure=False,
                 preset=None, selected_override=None):
    from . import manifest, selectables, selection, profile, wizard

    items = manifest.parse(config.manifest_path(root))
    overlay_present = bool(
        env.get("OVERLAY_DIR") or env.get("OVERLAY_REPO")
    )
    prof = profile.load(home)
    # A --preset or an adopted-share selection is headless by definition: it
    # names the id-set directly and skips both the wizard and the profile here.
    is_tty = (selected_override is None) and (not yes) and (preset is None) \
        and _stdin_is_tty()

    def _run_wizard(stages, preselected):
        # `existing` drives the splash status line (re-run vs fresh install).
        return wizard.run_wizard(stages, preselected, existing=prof is not None)

    if selected_override is not None:
        # Adopting a shared setup: the caller already resolved + persisted it.
        selected = set(selected_override)
    elif preset is not None:
        selected = _preset_ids(items, selectables.SELECTABLES,
                               overlay_present, preset)
    else:
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
    # (possibly updated) selection is what we save. A headless run (--yes /
    # --preset) or a plain profile replay must NOT (re)write it.
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
    for pack_id, status in report.packs.items():
        print("pack {0}\t{1}".format(pack_id, status))
    for name, status in report.mboard.items():
        print("mboard {0}\t{1}".format(name, status))
    _print_findings(report.scan_findings)
    for note in report.notes:
        print("note: {0}".format(note))

    # Styled post-install recap — interactive TTY only, ADDITIVE to the plain
    # output above. Guarded so a not-yet-landed wizard.render_summary can't
    # crash the install.
    if is_tty and _stdout_is_tty():
        render = getattr(wizard, "render_summary", None)
        if callable(render):
            summary = {
                "applied": list(report.base_applied) + list(report.overlay_applied),
                "plugins": dict(report.plugins),
                "packs": dict(report.packs),
                "mboard": dict(report.mboard),
                "notes": list(report.notes),
                "skipped": sorted(
                    _all_ids(items, selectables.SELECTABLES, overlay_present)
                    - set(selected)
                ),
            }
            try:
                render(summary, sys.stdout)
            except Exception as exc:
                print("note: summary render failed ({0})".format(exc))
    return 0


def _stdin_is_tty():
    try:
        return bool(sys.stdin.isatty())
    except Exception:
        return False


def _stdout_is_tty():
    try:
        return bool(sys.stdout.isatty())
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
    print("note: run `ccpkg status health` for an environment health report.")
    return 0


def _cmd_doctor(root, home, env, os_name):
    # doctor = environment health: deps, profile, mboard, and a drift SUMMARY
    # (distinct from `status`, which lists per-file drift).
    from collections import Counter
    from . import profile

    print("ccpkg status health")
    print("os\t{0}".format(os_name))
    for dep in ("git", "python3", "jq"):
        print("dep {0}\t{1}".format(dep, "present" if osenv.have(dep) else "MISSING"))

    prof = profile.load(home)
    if prof is None:
        print("profile\tnone (run `ccpkg apply`)")
    else:
        print("profile\t{0} selected".format(len(prof.selected)))

    sock = os.path.join(home, "mboard", "mboardd.sock")
    mb_dir = os.path.join(home, "mboard")
    if os.path.exists(sock):
        mb = "running"
    elif os.path.isdir(mb_dir):
        mb = "installed (daemon stopped)"
    else:
        mb = "absent"
    print("mboard\t{0}".format(mb))

    counts = Counter(status for _p, status in _compute_drift(root, home, os_name))
    print("drift\t{0} ok · {1} drift · {2} missing".format(
        counts.get("ok", 0), counts.get("drift", 0), counts.get("missing", 0)))
    if counts.get("drift", 0) or counts.get("missing", 0):
        print("note: run `ccpkg status` for per-file detail, then `ccpkg apply` "
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
        print("  …plus the mboard runtime and the saved profile. "
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


def _cmd_new(root, home, env, os_name, kind, name, group, default):
    # scaffold a new managed item: starter file + manifest entry.
    from . import scaffold
    try:
        created = scaffold.create(root, kind, name, group=group, default=default)
    except ValueError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 1
    print("created:")
    for p in created:
        print("  {0}".format(p))
    print("next: edit the new file and its 'desc' in manifest.json, then "
          "`ccpkg apply` to link it into ~/.claude.")
    return 0


def _cmd_overlay(root, home, env, os_name, action, dir, repo, git):
    # overlay init: scaffold a private overlay dir + wire it into local.env.
    from . import overlay
    if action != "init":
        print("usage: ccpkg new overlay [url]", file=sys.stderr)
        return 2
    dest = dir or os.path.join(config.user_config_dir(), "overlay")
    le = config.localenv_path(root)
    result = overlay.init(dest, le, repo=repo, do_git=git)
    print("overlay\t{0}".format(result["dest"]))
    if result.get("exists"):
        print("note: existing manifest.json kept (not clobbered)")
    for c in result["created"]:
        print("created\t{0}".format(c))
    print("localenv\t{0}\t({1})".format(le, result["localenv"]))
    print("git\t{0}".format("initialized" if result["git"] else "skipped"))
    print("note: add items with `ccpkg new`, then `ccpkg apply`.")
    return 0


def _cmd_diff(root, home, env, os_name, item):
    # diff = per-file CONTENT diff (expected -> live), complementing `status`.
    from . import diff
    try:
        results = diff.compute(root, home, os_name, only=item)
    except ValueError as exc:
        print("ccpkg status diff: {0}".format(exc), file=sys.stderr)
        return 2
    print(diff.render(results, only=item))
    drifted = any(status != "ok" for _p, status, _d in results)
    return 1 if drifted else 0


def _cmd_share(root, home, env, os_name, out):
    from . import share as share_mod, scan
    overlay_present = bool(env.get("OVERLAY_DIR") or env.get("OVERLAY_REPO"))
    data = share_mod.export_setup(root, home, overlay_present)
    # ids + labels from the public catalog -> base-pure by construction; verify
    # before publishing (ccpkg never emits a shareable file it hasn't scanned).
    findings = scan.scan_text_purity(
        json.dumps(data), scan.load_purity_terms(root), share_mod.SHARE_FILENAME)
    if findings:
        _print_findings(findings)
        print("error: refusing to write a share file with purity findings",
              file=sys.stderr)
        return 1
    out_path = out or os.path.join(os.getcwd(), share_mod.SHARE_FILENAME)
    share_mod.write_share(data, out_path)
    print("wrote {0}  ({1} items)".format(out_path, len(data["selected"])))
    print("share it: commit this to a repo, then anyone runs "
          "`ccpkg apply <repo-url>`  (or `ccpkg apply {0}`).".format(
              os.path.basename(out_path)))
    return 0


def _cmd_apply_share(root, home, env, os_name, source):
    from . import share as share_mod
    try:
        data = share_mod.fetch_share(source)
    except ValueError as exc:
        print("ccpkg apply: {0}".format(exc), file=sys.stderr)
        return 2
    return _adopt_share(root, home, env, os_name, data)


def _cmd_apply_template(root, home, env, os_name, name):
    from . import templates as templates_mod
    data = templates_mod.resolve_template(name, root)
    if data is None:
        print("ccpkg apply: unknown template: {0}".format(name), file=sys.stderr)
        return 2
    print("Starter template: {0}".format(name))
    desc = data.get("description")
    if desc:
        print("  " + desc)
    return _adopt_share(root, home, env, os_name, data)


def _adopt_share(root, home, env, os_name, data):
    # Shared adopt path for both remote shared setups and shipped templates:
    # intersect with this machine's catalog, preview, confirm on a TTY, then
    # persist the selection as the profile and install it.
    from . import share as share_mod
    overlay_present = bool(env.get("OVERLAY_DIR") or env.get("OVERLAY_REPO"))
    resolved, preview, skipped = share_mod.resolve_selection(
        data, root, overlay_present)
    if not resolved:
        print("ccpkg apply: nothing in this setup is available in your "
              "catalog", file=sys.stderr)
        return 1
    print("This setup installs {0} item(s):".format(len(preview)))
    for it in preview:
        print("  [{0}] {1}\t{2}".format(it["group"], it["id"], it["desc"]))
    if skipped:
        print("note: {0} not in your catalog, skipped: {1}".format(
            len(skipped), ", ".join(skipped)))
    # Trust gate: adopting a setup runs the installer (third-party plugins /
    # packs / MCP servers). Confirm on a TTY; CI/non-interactive runs straight.
    if _stdin_is_tty():
        try:
            resp = input("Apply this setup? [y/N] ").strip().lower()
        except EOFError:
            resp = ""
        if resp not in ("y", "yes"):
            print("apply cancelled")
            return 130
    return _install_selection(root, home, env, os_name, resolved, overlay_present)


def _install_selection(root, home, env, os_name, resolved, overlay_present):
    # Persist a resolved id-set as this machine's profile, then install it.
    # The no-confirm core shared by adopt (_adopt_share) and `suggest`.
    from . import share as share_mod, profile
    all_ids = share_mod.catalog_ids(root, overlay_present)
    profile.save(home, profile.Profile(
        selected=sorted(resolved), deselected=sorted(all_ids - resolved)))
    return _cmd_install(root, home, env, os_name, selected_override=resolved)


def _cmd_gallery(root, home, env, os_name, action):
    # browse community setups, or regenerate the GALLERY.md index.
    from . import gallery as gallery_mod
    overlay_present = bool(env.get("OVERLAY_DIR") or env.get("OVERLAY_REPO"))
    if action == "index":
        path = gallery_mod.write_index(root, overlay_present)
        print("wrote {0}".format(path))
        return 0
    entries = gallery_mod.list_entries(root, overlay_present)
    if not entries:
        print("no gallery entries yet (add a gallery/<name>.share.json)")
        return 0
    print("Community setups (ranked):")
    for e in entries:
        print("  {0}/100 {1}  {2}\t{3}".format(
            e["score"], e["grade"], e["name"], e["description"]))
        print("        adopt: ccpkg apply gallery/{0}".format(e["file"]))
    return 0


def _cmd_card(root, home, env, os_name, out):
    # render a shareable SVG card of this setup to a file.
    from . import card as card_mod
    overlay_present = bool(env.get("OVERLAY_DIR") or env.get("OVERLAY_REPO"))
    stats = card_mod.build_stats(root, home, overlay_present)
    svg = card_mod.render_svg(stats)
    out_path = out or os.path.join(os.getcwd(), "ccpkg-card.svg")
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(svg)
    except OSError as exc:
        print("ccpkg card: {0}".format(exc), file=sys.stderr)
        return 1
    print("wrote {0}  (score {1}/100, grade {2})".format(
        out_path, stats["score"], stats["grade"]))
    print("embed it:  ![my Claude Code setup]({0})".format(
        os.path.basename(out_path)))
    return 0


def _cmd_score(root, home, env, os_name):
    # grade this machine's setup (saved profile, or the default-on set) 0-100.
    from . import share as share_mod, score as score_mod
    overlay_present = bool(env.get("OVERLAY_DIR") or env.get("OVERLAY_REPO"))
    selected = set(share_mod.export_setup(root, home, overlay_present)["selected"])
    catalog = share_mod._catalog(root, overlay_present)
    r = score_mod.analyze(selected, catalog)
    print("Your setup: {0} / 100  ({1})".format(r.score, r.grade))
    for name, got, mx in r.dimensions:
        filled = int(round(10 * got / mx)) if mx else 0
        bar = "#" * filled + "-" * (10 - filled)
        print("  [{0}] {1:<22} {2}/{3}".format(bar, name, got, mx))
    if r.strengths:
        print("strengths:")
        for s in r.strengths:
            print("  + " + s)
    if r.suggestions:
        print("suggestions:")
        for s in r.suggestions:
            print("  - " + s)
    return 0


def _cmd_suggest(root, home, env, os_name, action):
    # detect the cwd project and configure Claude Code for it. Default = apply;
    # `suggest preview` shows the recommendation and changes nothing.
    from . import suggest as suggest_mod, share as share_mod, mcp as mcp_mod
    overlay_present = bool(env.get("OVERLAY_DIR") or env.get("OVERLAY_REPO"))
    signals = suggest_mod.detect(os.getcwd())
    cat = share_mod._catalog(root, overlay_present)
    selected, mcp_ids, rationale = suggest_mod.recommend(signals, set(cat))
    valid_mcp = [m for m in mcp_ids if m in mcp_mod.by_id()]

    print("Detected: {0}".format(", ".join(sorted(signals)) or "no strong signals"))
    why = {r["id"]: r["why"] for r in rationale}
    print("Recommended setup ({0} items):".format(len(selected) + len(valid_mcp)))
    for sid in selected:
        group = cat.get(sid, ("", ""))[0]
        print("  [{0}] {1}\t{2}".format(group, sid, why.get(sid, "")))
    for m in valid_mcp:
        print("  [MCP] {0}\t-> ./.mcp.json".format(m))

    if action == "preview":
        print("\n(preview only — nothing applied; run `ccpkg suggest` to apply)")
        return 0

    if valid_mcp:
        mcp_mod.apply_servers(valid_mcp, mcp_mod.mcp_json_path())
        print("wrote {0} MCP server(s) to ./.mcp.json".format(len(valid_mcp)))
    rc = _install_selection(root, home, env, os_name, set(selected), overlay_present)
    if rc == 0:
        print("configured Claude Code for this project "
              "({0} items applied)".format(len(selected)))
    return rc


def _cmd_mcp(action, names):
    # manage curated MCP servers in the project-scope ./.mcp.json (cwd).
    from . import mcp as mcp_mod
    if action == "list":
        present = mcp_mod.present_ids(mcp_mod.mcp_json_path())
        for srv in mcp_mod.MCP_CATALOG:
            mark = "*" if srv.id in present else " "
            print("{0} {1:<14} {2:<5} {3}".format(
                mark, srv.id, srv.transport, srv.desc))
        print("\n* = already in ./.mcp.json    add: ccpkg mcp add <name>")
        return 0
    if action == "add":
        if not names:
            print("usage: ccpkg mcp add <name> [name ...]", file=sys.stderr)
            return 2
        unknown = [n for n in names if n not in mcp_mod.by_id()]
        if unknown:
            print("ccpkg mcp: unknown server(s): {0}".format(", ".join(unknown)),
                  file=sys.stderr)
            print("known: {0}".format(", ".join(mcp_mod.catalog_ids())),
                  file=sys.stderr)
            return 2
        result = mcp_mod.apply_servers(names, mcp_mod.mcp_json_path())
        for label in ("added", "updated", "present"):
            if result[label]:
                print("{0}: {1}".format(label, ", ".join(result[label])))
        print("-> {0}".format(result["path"]))
        if result["vars"]:
            print("set these env vars (shell profile or ~/.claude/settings.local.json):")
            for v in result["vars"]:
                print("  ${0}".format(v))
        return 0
    print("usage: ccpkg mcp {list,add}", file=sys.stderr)
    return 2


def _cmd_completions(shell):
    # print a shell completion script (zsh|bash) or the dynamic `items` feed.
    from . import completions
    if shell == "items":
        for path in completions.list_items():
            print(path)
        return 0
    if shell == "templates":
        from . import templates as templates_mod
        for name in templates_mod.list_templates():
            print(name)
        return 0
    if shell == "mcp":
        from . import mcp as mcp_mod
        for sid in mcp_mod.catalog_ids():
            print(sid)
        return 0
    script = completions.render(shell)
    if script is None:
        print("usage: ccpkg completions {zsh,bash,items,templates,mcp}",
              file=sys.stderr)
        return 2
    sys.stdout.write(script)
    return 0


def _build_parser():
    parser = argparse.ArgumentParser(prog="ccpkg")
    parser.add_argument(
        "--version", action="version", version="ccpkg " + __version__
    )
    sub = parser.add_subparsers(dest="cmd")
    # apply — install / re-apply the env (interactive if no preset given)
    p_apply = sub.add_parser(
        "apply", help="install / re-apply, a preset, or adopt a shared setup")
    p_apply.add_argument(
        "source", nargs="?", default=None, metavar="[preset|template|url|path]",
        help="a preset (minimal|recommended|everything), a starter template "
             "name, a shared setup's git URL or path, or omit for the "
             "interactive picker")

    # status — inspect: drift (default) + diff / health / scan sub-verbs
    p_status = sub.add_parser("status", help="inspect: drift / diff / health / scan")
    st_sub = p_status.add_subparsers(dest="status_action")
    p_st_diff = st_sub.add_parser("diff", help="content diff (expected -> live)")
    p_st_diff.add_argument("item", nargs="?", default=None,
                           help="optional manifest path (e.g. agents/debugger.md)")
    st_sub.add_parser("health", help="deps / profile / mboard / drift summary")
    st_sub.add_parser("scan", help="base purity + secrets scan")

    # new — scaffold a managed item (agent/command/hook/skill) or the overlay
    p_new = sub.add_parser("new", help="scaffold a managed item or the overlay")
    new_sub = p_new.add_subparsers(dest="new_kind")
    for _kind in ("agent", "command", "hook", "skill"):
        p_k = new_sub.add_parser(_kind, help="scaffold a %s (file + manifest entry)" % _kind)
        p_k.add_argument("name", help="lowercase name matching ^[a-z0-9][a-z0-9-]*$")
    p_new_ov = new_sub.add_parser("overlay", help="scaffold + wire the private overlay")
    p_new_ov.add_argument("url", nargs="?", default=None,
                          help="optional git URL (sets OVERLAY_REPO instead of OVERLAY_DIR)")

    # push — capture live ~/.claude edits back into the repo
    p_push = sub.add_parser("push", help="capture live ~/.claude edits back into the repo")
    p_push.add_argument("paths", nargs="*")

    # uninstall — remove managed files (the one destructive op; keeps its guard)
    p_uninstall = sub.add_parser("uninstall",
                                 help="remove managed files, restore backups")
    p_uninstall.add_argument("--yes", "--non-interactive", dest="yes",
                             action="store_true",
                             help="skip the confirmation prompt")

    # share — export your setup to a portable, base-pure ccpkg.share.json
    p_share = sub.add_parser(
        "share", help="export your setup to a shareable ccpkg.share.json")
    p_share.add_argument("out", nargs="?", default=None,
                         help="output path (default: ./ccpkg.share.json)")

    # score — grade this machine's setup 0-100 with upgrade suggestions
    sub.add_parser("score", help="grade your Claude Code setup 0-100 + suggest upgrades")

    # card — render a shareable SVG card of this setup
    p_card = sub.add_parser("card", help="render a shareable SVG card of your setup")
    p_card.add_argument("out", nargs="?", default=None,
                        help="output path (default: ./ccpkg-card.svg)")

    # gallery — browse community setups; `gallery index` regenerates GALLERY.md
    p_gallery = sub.add_parser("gallery", help="browse community setups to adopt")
    gal_sub = p_gallery.add_subparsers(dest="gallery_action")
    gal_sub.add_parser("index", help="regenerate GALLERY.md from gallery/*.share.json")

    # suggest — detect the cwd project and auto-configure Claude Code for it
    p_suggest = sub.add_parser(
        "suggest", help="detect this project and auto-configure Claude Code for it")
    sug_sub = p_suggest.add_subparsers(dest="suggest_action")
    sug_sub.add_parser("preview", help="show the recommendation without applying")

    # mcp — manage curated MCP servers in the project-scope ./.mcp.json
    p_mcp = sub.add_parser("mcp", help="manage curated MCP servers in ./.mcp.json")
    mcp_sub = p_mcp.add_subparsers(dest="mcp_action")
    mcp_sub.add_parser("list", help="list the curated MCP-server catalog")
    p_mcp_add = mcp_sub.add_parser(
        "add", help="deep-merge catalog server(s) into ./.mcp.json")
    p_mcp_add.add_argument("names", nargs="*", metavar="name",
                           help="catalog server id(s) to add")

    # completions — print a shell completion script (or the dynamic items feed)
    p_comp = sub.add_parser(
        "completions", help="print a shell completion script (zsh|bash)")
    p_comp.add_argument("shell", nargs="?", default=None,
                        metavar="[zsh|bash|items|templates]",
                        help="zsh|bash prints a script; items/templates list "
                             "manifest paths / template names (TAB-time feeds)")
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2
    root, home, env, os_name = _resolve()
    if args.cmd == "apply":
        source = getattr(args, "source", None)
        # A preset word (or nothing) -> the install/wizard flow; anything else
        # (a git URL or a path) -> adopt that shared setup.
        if source is None or source in ("minimal", "recommended", "everything"):
            return _cmd_install(root, home, env, os_name, yes=False,
                                reconfigure=False, preset=source)
        # a known starter-template name -> adopt its shipped share file;
        # otherwise treat the source as a git URL or local path.
        from . import templates as templates_mod
        if source in templates_mod.list_templates(root):
            return _cmd_apply_template(root, home, env, os_name, source)
        return _cmd_apply_share(root, home, env, os_name, source)
    if args.cmd == "status":
        action = getattr(args, "status_action", None)
        if action == "diff":
            return _cmd_diff(root, home, env, os_name, getattr(args, "item", None))
        if action == "health":
            return _cmd_doctor(root, home, env, os_name)
        if action == "scan":
            return _cmd_scan(root, home, env, os_name)
        return _cmd_status(root, home, env, os_name)
    if args.cmd == "new":
        kind = getattr(args, "new_kind", None)
        if kind is None:
            print("usage: ccpkg new {agent,command,hook,skill,overlay} ...",
                  file=sys.stderr)
            return 2
        if kind == "overlay":
            return _cmd_overlay(root, home, env, os_name, action="init",
                                dir=None, repo=getattr(args, "url", None), git=False)
        return _cmd_new(root, home, env, os_name, kind, args.name, None, None)
    if args.cmd == "push":
        return _cmd_push(root, home, env, os_name, args.paths)
    if args.cmd == "uninstall":
        return _cmd_uninstall(root, home, env, os_name,
                              yes=getattr(args, "yes", False))
    if args.cmd == "share":
        return _cmd_share(root, home, env, os_name, getattr(args, "out", None))
    if args.cmd == "score":
        return _cmd_score(root, home, env, os_name)
    if args.cmd == "card":
        return _cmd_card(root, home, env, os_name, getattr(args, "out", None))
    if args.cmd == "gallery":
        return _cmd_gallery(root, home, env, os_name,
                            getattr(args, "gallery_action", None))
    if args.cmd == "suggest":
        return _cmd_suggest(root, home, env, os_name,
                            getattr(args, "suggest_action", None))
    if args.cmd == "mcp":
        return _cmd_mcp(getattr(args, "mcp_action", None),
                        getattr(args, "names", []))
    if args.cmd == "completions":
        return _cmd_completions(getattr(args, "shell", None))
    parser.print_help()
    return 2
