# claude-setup

Claude Code environment as code. A single repository you can hand to a fresh Claude Code
install — on macOS or Ubuntu — and have your entire non-vanilla setup reconstructed:
settings, hooks, statusline, cost scripts, commands, skills, plugin/marketplace choices,
and the vendored mailbox coordinator. Secrets and personal/company content never enter
this repo.

## Quick start

```sh
git clone <this-repo-url> claude-setup
cd claude-setup
cp local.env.example local.env   # edit per-machine values (optional)
./install.sh
```

`install.sh` ensures `git`, `python3`, and `jq` are present (via `brew`/`apt`), then runs
`python3 -m ccpkg install`. For a step-by-step, verifiable walkthrough, see
[SETUP.md](./SETUP.md). For how Claude reconstructs the environment, see
[CLAUDE.md](./CLAUDE.md).

### Interactive install

Run in a terminal, `ccpkg install` opens an interactive feature picker. Features are
grouped into staged screens (Core, Commands, Skills, Plugins, Coordination, and an Overlay
stage when an overlay is configured). Use the arrow keys to move, space to toggle an item,
Enter to advance to the next stage, and Esc to go back. Your choice is saved to
`~/.claude/.ccpkg-profile.json` and replayed automatically on later runs.

```text
Interactive install
  ccpkg install              # feature picker (when run in a terminal)
  ccpkg install --yes        # headless: apply saved profile or defaults
  ccpkg install --reconfigure  # re-open the picker
Selections persist to ~/.claude/.ccpkg-profile.json.
```

`--yes` (alias `--non-interactive`) is fully headless — it applies the saved profile, or
the defaults if none exists, with no prompts. `install.sh` uses it so the bootstrap never
blocks. `--reconfigure` re-opens the picker even when a profile already exists.

## The base / overlay model

The setup is split into two layers so the public repo stays clean and shareable:

- **Base — this repo.** Fully scrubbed: no PII, no company-specifics, no secrets. The base
  alone yields a complete, generic environment. It is the source of truth for portable
  customization.
- **Overlay — a separate private repo or directory.** Same `home/.claude/` mirror
  structure, holding only personal/company content. It layers on top of the base, adding
  new files and merging extra `settings`/allowlist entries.

Configure the overlay in `local.env` (both optional):

- `OVERLAY_REPO=<git url>` — a private overlay repo the installer clones and applies; or
- `OVERLAY_DIR=<path>` — a local overlay directory.

If neither is set, only the base applies and the system is fully functional (just
generic). `ccpkg install` always applies **base, then overlay (if present)** using the
same machinery.

## How it is organized

```
claude-setup/
  CLAUDE.md            # Claude reads this first: "to reconstruct, run ./install.sh OR follow SETUP.md"
  SETUP.md             # ordered, verifiable reconstruction playbook
  README.md            # this file
  install.sh           # bash bootstrap -> python3 -m ccpkg install
  local.env.example    # per-machine variables template
  manifest.json        # declarative managed-set: path, mode, os, layer
  home/.claude/        # source-of-truth mirror of the portable (base) setup
  mailbox/             # vendored mailbox coordinator ($HOME-relative hooks)
  ccpkg/               # Python installer/CLI (stdlib only, python3 >= 3.9)
  .githooks/pre-commit # runs `ccpkg scan`; blocks commits with secrets/PII
```

## The `ccpkg` tool

`python3 -m ccpkg <command>` (no third-party dependencies):

| Command | What it does |
| --- | --- |
| `install` | Fresh-machine bootstrap (idempotent): deps, base, overlay, plugins, mailbox, scan, re-auth notes. |
| `pull` | Re-apply repo to live `~/.claude` (symlink/template/merge; backs up first). |
| `push [paths...]` | Capture changed live files into the right layer; reverse-templatize machine values; secret-scan. No auto-commit. |
| `status` / `doctor` | Report drift between the repo and live, plus a health note. |
| `scan` | Secrets + base-purity scan; exits non-zero on findings. Also the pre-commit hook. |

## Sync model

Each managed item declares a `mode` in `manifest.json`:

- **`symlink`** — OS/path-agnostic hand-authored content (statusline, cost scripts,
  commands, generic skills). The repo file IS the live file.
- **`template`** — files containing `${VAR}` machine values. Copied with substitution and
  regenerated on `pull`.
- **`merge`** — Claude-managed JSON (`settings.json`). Deep-merged into the live file
  (base-managed keys win, live-only keys preserved), so Claude Code can still rewrite it
  live; reconciled via `push`.

## Adding a feature

1. Add the file under `home/.claude/` (base) or your overlay's mirror.
2. Add a matching entry to `manifest.json`:

   ```json
   {
     "items": [
       { "path": "commands/my-command.md", "mode": "symlink", "os": "any", "layer": "base" }
     ]
   }
   ```

   Choose `mode` (`symlink` | `template` | `merge`), `os` (`any` | `darwin` | `linux`),
   and `layer` (`base` for generic/shareable, `overlay` for personal/company).
3. Run the scan and apply, then commit (base) or push to your overlay:

   ```sh
   python3 -m ccpkg scan
   python3 -m ccpkg pull
   git add -A && git commit -m "feat: add my-command"
   ```

   The pre-commit hook re-runs `ccpkg scan` and blocks the commit if it finds secrets or
   base-purity (PII/company) content — move such content to the overlay or templatize it
   with `${VAR}`.

## Secrets and portability

- Credentials never enter git (either layer). A fresh machine re-authenticates with
  `claude auth login` (or a credential token in the environment). See
  [SETUP.md](./SETUP.md) Step 7.
- Cross-platform by construction: `$HOME`/`~` where the shell expands, `${VAR}` templating
  for the rest, and an OS-aware installer (`brew`/`apt`, BSD/GNU `stat`).
- Every apply backs up before overwrite (`*.ccpkg.bak`) and is idempotent.

## Scope

Supports macOS and Ubuntu. Does not sync machine state/history, does not store encrypted
secrets in git (it excludes and re-auths instead), and does not auto-publish or manage the
repo's GitHub remote.

## Private overlay

The public base in this repo is fully scrubbed and generic. Personal/company content
(your personal `<name>-*` agents, any company-specific skills, AWS allowlist, vault
wiring) lives in a **separate private overlay**, configured via `OVERLAY_REPO` or
`OVERLAY_DIR` in `local.env`. With neither set, only the generic base applies — which is
what keeps this repo publicly shareable.

See [`docs/overlay-example/`](docs/overlay-example/) for the exact overlay layout (its
own `manifest.json` with `layer="overlay"` items + a `home/.claude/` mirror) and the
local migration steps. Migrating real personal content into the overlay is a LOCAL action
and is never committed to this base repo.
