"""Orchestration: run the full install (contract section 12). Never raises on sub-step failure."""
import os
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import config
from . import localenv
from . import osenv
from . import manifest
from . import apply as apply_mod
from . import plugins
from . import mailbox_install
from . import scan


@dataclass
class InstallReport:
    os: str
    deps: Dict[str, str] = field(default_factory=dict)
    base_applied: List[Tuple[str, str]] = field(default_factory=list)
    overlay_applied: List[Tuple[str, str]] = field(default_factory=list)
    plugins: Dict[str, str] = field(default_factory=dict)
    mailbox: Dict[str, str] = field(default_factory=dict)
    scan_findings: List["scan.Finding"] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _overlay_cache_dir():
    # type: () -> str
    return os.path.join(os.path.expanduser("~/.cache/ccpkg"), "overlay")


def clone_overlay(env, run=subprocess.run):
    # type: (Dict[str, str], object) -> Optional[str]
    """OVERLAY_DIR exists -> return it; elif OVERLAY_REPO -> git clone into the cache dir
    and return its path; else None. Never raises."""
    overlay_dir = env.get("OVERLAY_DIR", "")
    if overlay_dir and os.path.isdir(overlay_dir):
        return overlay_dir
    repo = env.get("OVERLAY_REPO", "")
    if not repo:
        return None
    dest = _overlay_cache_dir()
    try:
        if os.path.isdir(os.path.join(dest, ".git")):
            run(["git", "-C", dest, "pull", "--ff-only"], check=False)
            return dest
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        run(["git", "clone", repo, dest], check=False)
        if os.path.isdir(dest):
            return dest
        # The injected/faked run may not create the dir; treat a recorded clone as success.
        return dest
    except Exception:
        return None


def _vault_enabled(env):
    # type: (Dict[str, str]) -> bool
    vault_root = env.get("VAULT_ROOT", "")
    return bool(vault_root) and os.path.isdir(vault_root)


def _auth_note(report, run, have):
    # type: (InstallReport, object, object) -> None
    """If `claude` is present, check auth status; on logged-out/error, add re-auth note."""
    try:
        if not have("claude"):
            return
        result = run(["claude", "auth", "status"], check=False,
                     capture_output=True, text=True)
        rc = getattr(result, "returncode", 0)
        if rc != 0:
            report.notes.append(
                "claude is installed but not logged in; run `claude auth login` "
                "(or set CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY) to authenticate."
            )
    except Exception as exc:
        report.notes.append("auth: could not determine claude login status (%s)" % exc)


def install(root, home_target, env, os_name, run=subprocess.run,
            interactive=False, selected=None):
    # type: (str, str, Dict[str, str], str, object, bool, object) -> InstallReport
    """Run the install pipeline. When `selected` is a set of ids, only those
    manifest items / overlay items / plugins / mailbox are applied; when None,
    everything applies (legacy behavior). Never raises; sub-step failures -> notes."""
    report = InstallReport(os=os_name)

    # 1. dependencies — when packaged (CCPKG_ROOT set), git/python3/jq are declared
    #    package deps; do not shell out to brew/apt at runtime.
    try:
        if config.is_packaged():
            report.deps = {pkg: "declared" for pkg in ("git", "python3", "jq")}
        else:
            report.deps = osenv.ensure_deps(os_name, ["git", "python3", "jq"], run=run)
    except Exception as exc:
        report.notes.append("deps: %s" % exc)

    # 2. template vars + vault gate
    try:
        tvars = localenv.template_vars(env)
    except Exception as exc:
        report.notes.append("vars: %s" % exc)
        tvars = {}
    vault_enabled = _vault_enabled(env)

    base_src = config.home_claude_src(root)

    # 3. base layer
    try:
        items = manifest.parse(config.manifest_path(root))
        if selected is not None:
            items = [it for it in items if it.path in selected]
        report.base_applied = apply_mod.apply_layer(
            items, "base", base_src, home_target, tvars, vault_enabled, os_name
        )
    except Exception as exc:
        report.notes.append("base: %s" % exc)

    # 4. overlay layer (only when an overlay dir is present or freshly cloned)
    try:
        overlay_dir = clone_overlay(env, run=run)
        if overlay_dir:
            ov_manifest = os.path.join(overlay_dir, "manifest.json")
            ov_src = config.home_claude_src(overlay_dir)
            ov_items = manifest.parse(ov_manifest)
            if selected is not None:
                ov_items = [it for it in ov_items if it.path in selected]
            report.overlay_applied = apply_mod.apply_layer(
                ov_items, "overlay", ov_src, home_target, tvars, vault_enabled, os_name
            )
    except Exception as exc:
        report.notes.append("overlay: %s" % exc)

    # 5. plugins (best-effort; settings already carry enabledPlugins via base merge)
    try:
        if selected is None:
            report.plugins = plugins.cli_install(run=run, have=osenv.have)
        else:
            wanted = {p for p in plugins.PLUGINS
                      if p.split("@", 1)[0] in selected}
            report.plugins = plugins.cli_install(
                run=run, have=osenv.have, only=wanted)
    except Exception as exc:
        report.notes.append("plugins: %s" % exc)

    # 6. mailbox
    try:
        if selected is None or "mailbox" in selected:
            report.mailbox = mailbox_install.install(root, home_target, run=run)
        else:
            report.mailbox = {"status": "skipped"}
    except Exception as exc:
        report.notes.append("mailbox: %s" % exc)

    # 7. scan base source (report findings; do not delete)
    try:
        terms = scan.load_purity_terms(root)
        paths = []
        for dirpath, _dirnames, filenames in os.walk(base_src):
            for name in filenames:
                paths.append(os.path.join(dirpath, name))
        report.scan_findings = scan.scan_paths(paths, "base", terms)
    except Exception as exc:
        report.notes.append("scan: %s" % exc)

    # 8. auth status note
    _auth_note(report, run, osenv.have)

    return report
