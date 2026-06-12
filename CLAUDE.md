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
   `python3 -m ccpkg install` from the repo root.

2. **Step by step (preferred when you want to verify each stage):** follow
   [SETUP.md](./SETUP.md). It is an ordered, verifiable playbook: each step has an exact
   command and an expected result you can check before moving on.

Do **not** hand-edit `~/.claude/settings.json` or other managed files to reproduce this
setup. The `ccpkg` tool performs JSON deep-merge, `${VAR}` templating, symlinking, and
secret/PII scanning deterministically. Hand-editing risks drift and leaks.

## What `ccpkg` does

`python3 -m ccpkg <command>`:

- `install` — fresh-machine bootstrap (idempotent): load `local.env`, ensure OS deps,
  apply the base layer, apply the private overlay if configured, reinstall plugins,
  install the vendored mboard, scan for secrets/PII, and print re-auth instructions.
- `pull` — re-apply the repo to the live `~/.claude` (symlink/template/merge; backs up
  before overwrite). No deps/plugins/mboard work.
- `push [paths...]` — capture changed live files back into the correct layer's working
  tree (classify via `manifest.json`, reverse-templatize machine values to `${VAR}`,
  secret-scan). Never auto-commits.
- `status` / `doctor` — report drift between the repo and the live `~/.claude`.
- `scan` — secrets + base-purity scan; exits non-zero if anything is found. Also run by
  the pre-commit hook.

## Layers

- **Base (this repo):** fully scrubbed and safe to share. No PII, no company-specifics,
  no secrets. The base alone produces a complete, generic environment.
- **Overlay (separate private repo or directory):** holds personal/company content and
  layers on top. Configured by `OVERLAY_REPO` or `OVERLAY_DIR` in `local.env`. If neither
  is set, only the base is applied.

## Secrets

Credentials never live in git. A fresh machine re-authenticates — see the re-auth step in
[SETUP.md](./SETUP.md). The scan blocks any commit that contains a credential file or a
secret-looking token.

## Where things live

- `manifest.json` — the declarative managed-set: one entry per item with `path`, `mode`
  (`symlink` | `template` | `merge`), `os` (`any` | `darwin` | `linux`), and `layer`
  (`base` | `overlay`). Adding a feature = add an entry plus the file.
- `home/.claude/` — the source-of-truth mirror of the portable (base) setup.
- `mboard/` — vendored mboard coordinator source ($HOME-relative hooks).
- `ccpkg/` — the installer/CLI package.

Start with [SETUP.md](./SETUP.md) to reconstruct, or [README.md](./README.md) for a human
overview of the model.
