#!/usr/bin/env bash
set -euo pipefail

# --- resolve this script's directory (repo root), following symlinks ---
_source="${BASH_SOURCE[0]}"
if command -v realpath >/dev/null 2>&1; then
  _source="$(realpath "$_source")"
elif command -v readlink >/dev/null 2>&1; then
  # follow symlinks where readlink -f is available (GNU); fall back otherwise
  _resolved="$(readlink -f "$_source" 2>/dev/null || true)"
  if [ -n "$_resolved" ]; then
    _source="$_resolved"
  fi
fi
REPO_ROOT="$(cd "$(dirname "$_source")" && pwd -P)"

export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# --- python3 must exist to drive ccpkg (read-only OS detection needs it too) ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "install.sh: python3 is required but was not found on PATH." >&2
  echo "install.sh: install python3 (brew install python3 / sudo apt-get install -y python3) and re-run." >&2
  exit 1
fi

# --- detect OS via ccpkg.osenv (single source of truth; read-only) ---
OS_NAME="$(python3 -c 'import ccpkg.osenv as o; print(o.detect_os())')"
# Headless apply of the saved profile/defaults: `apply` with NO preset, stdin
# redirected from /dev/null so ccpkg auto-detects a non-interactive session and
# replays the saved profile (a preset would override it — we don't want that).
CMD="python3 -m ccpkg apply </dev/null"
echo "install.sh: repo root: $REPO_ROOT"
echo "install.sh: detected os: $OS_NAME"

# --- dry-run: print the plan and stop BEFORE touching the machine ---
# ensure_deps (below) attempts brew/apt installs for missing pkgs, so the
# dry-run short-circuit MUST precede it. Nothing above this point mutates state.
if [ -n "${CCPKG_DRYRUN:-}" ]; then
  echo "install.sh: DRYRUN set; would exec: $CMD"
  echo "install.sh: with PYTHONPATH=$PYTHONPATH"
  exit 0
fi

# --- ensure git/python3/jq via ccpkg.osenv.ensure_deps (brew/apt aware) ---
DEPS_REPORT="$(python3 - "$OS_NAME" <<'PY'
import sys
import ccpkg.osenv as osenv
os_name = sys.argv[1]
report = osenv.ensure_deps(os_name, ["git", "python3", "jq"])
missing = [pkg for pkg, status in report.items() if status == "missing"]
for pkg in missing:
    print("MISSING " + pkg)
PY
)"
if [ -n "$DEPS_REPORT" ]; then
  echo "install.sh: the following dependencies could not be installed:" >&2
  echo "$DEPS_REPORT" >&2
  echo "install.sh: install them manually, then re-run ./install.sh" >&2
fi

# --- hand off to the Python installer (headless: stdin from /dev/null) ---
exec python3 -m ccpkg apply </dev/null
