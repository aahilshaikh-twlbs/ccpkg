# CLAUDE.md — claude-setup

This repository is a self-describing, environment-as-code definition of a customized
Claude Code setup (settings, hooks, statusline, cost scripts, commands, skills, plugin
choices, and a vendored mboard coordinator). It is built so that **you, Claude, can
reconstruct the entire non-vanilla environment on a fresh machine** without hand-editing
JSON or guessing at steps.

## How to reconstruct this environment

There are two equivalent paths. Both run the same deterministic logic in the `ccpkg`
Python tool (no third-party dependencies, system `python3` >= 3.9, macOS or Ubuntu).

1. **Headless (preferred for a clean machine):**

   ```sh
   ./install.sh
   ```

   This ensures `git`, `python3`, and `jq` are present (via `brew`/`apt`), then runs
   `python3 -m ccpkg apply` from the repo root.

2. **Step by step (preferred when you want to verify each stage):** follow
   [SETUP.md](./SETUP.md). It is an ordered, verifiable playbook: each step has an exact
   command and an expected result you can check before moving on.

Do **not** hand-edit `~/.claude/settings.json` or other managed files to reproduce this
setup. The `ccpkg` tool performs JSON deep-merge, `${VAR}` templating, symlinking, and
secret/PII scanning deterministically. Hand-editing risks drift and leaks.

## What `ccpkg` does

`python3 -m ccpkg <verb>`:

- `apply [minimal|recommended|everything|<template>|<url>|<path>]` — install / re-apply the
  environment (idempotent): load `local.env`, ensure OS deps, apply the base layer, apply the
  private overlay if configured, reinstall plugins, install the vendored mboard, scan for
  secrets/PII, and print re-auth instructions. Opens an interactive feature picker when run
  in a terminal with no preset; runs headlessly when given a preset or when stdin is not a
  TTY. Re-running reopens the picker, so there is no separate lightweight re-apply. A
  **starter-template name** (`web-dev`/`backend`/`research`/`the-works`, shipped under
  `templates/`) applies a curated persona by adopting its committed `ccpkg.share.json`.
- `status` — drift summary between the repo and the live `~/.claude` (the default).
  - `status diff [item]` — content diff for managed items.
  - `status health` — deps/profile/mboard/drift health report.
  - `status scan` — secrets + base-purity scan; exits non-zero if anything is found. Also
    run by the pre-commit hook and CI.
- `new <kind> <name>` — scaffold a managed item (`agent` | `command` | `hook` | `skill`).
  `new overlay [url]` scaffolds and wires up the private overlay.
- `push [paths...]` — capture changed live files back into the correct layer's working
  tree (classify via `manifest.json`, reverse-templatize machine values to `${VAR}`,
  secret-scan). Never auto-commits.
- `uninstall [--yes]` — remove managed files (restoring `*.ccpkg.bak` backups), drop the
  mboard runtime and saved profile. Confirms first unless `--yes`.
- `share [out]` — export your selection to a portable, base-pure `ccpkg.share.json`. Commit
  it to a repo and anyone reconstructs your setup with `ccpkg apply <repo-url>`. (`apply`
  also accepts a git URL or a path to a share file — it previews + confirms before
  installing, since adopting a setup installs its third-party plugins/packs/MCP servers.)
- `completions [zsh|bash|items|templates|mcp]` — `zsh`/`bash` print a shell completion script
  to stdout (you install it; ccpkg never edits your shell rc). The verb tree is introspected
  from the live parser, so it can't drift. `items`/`templates`/`mcp` print the manifest paths
  / template names / MCP catalog ids the generated scripts call for TAB-time completion.
- `mcp list` / `mcp add <name...>` — manage a curated catalog of MCP servers in the
  **project-scope `./.mcp.json`** (deep-merge, idempotent, preserves your own servers).
  Deliberately never writes `~/.claude.json` (Claude Code's mutable state file). Credentials
  stay as `${VAR}` references that Claude Code expands at connect time — the catalog is
  base-pure. (Local MCP servers only; the `mcp__claude_ai_*` tools are remote claude.ai
  account integrations and are not managed here.)

## Layers

- **Base (this repo):** fully scrubbed and safe to share. No PII, no company-specifics,
  no secrets. The base alone produces a complete, generic environment.
- **Overlay (separate private repo or directory):** holds personal/company content and
  layers on top. Configured by `OVERLAY_REPO` or `OVERLAY_DIR` in `local.env`. If neither
  is set, only the base is applied.

## Secrets

Credentials never live in git. A fresh machine re-authenticates — see the re-auth step in
[SETUP.md](./SETUP.md). `ccpkg status scan` blocks any commit that contains a credential
file or a secret-looking token.

## Where things live

- `manifest.json` — the declarative managed-set: one entry per item with `path`, `mode`
  (`symlink` | `template` | `merge`), `os` (`any` | `darwin` | `linux`), and `layer`
  (`base` | `overlay`). Adding a feature = add an entry plus the file.
- `home/.claude/` — the source-of-truth mirror of the portable (base) setup.
- `mboard/` — vendored mboard coordinator source ($HOME-relative hooks).
- `ccpkg/` — the installer/CLI package.

Start with [SETUP.md](./SETUP.md) to reconstruct, or [README.md](./README.md) for a human
overview of the model.
