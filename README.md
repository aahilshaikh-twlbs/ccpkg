# ccpkg

Your Claude Code environment as code. `ccpkg` is a dependency-free Python tool that
reconstructs a complete, non-vanilla Claude Code setup — settings, hooks, statusline, cost
scripts, commands, skills, plugin/marketplace choices, and a vendored mailbox coordinator —
from a single repository, on a fresh macOS or Ubuntu machine. Personal, company, and secret
content never enters the public repo; it lives in an optional private overlay you point the
tool at.

## Install

### Homebrew (recommended)

The formula lives in this repo, so the tap is added by URL:

```sh
brew tap aahilshaikh-twlbs/ccpkg https://github.com/aahilshaikh-twlbs/ccpkg
brew install ccpkg
ccpkg --version
```

This installs the bundled payload into Homebrew's `libexec` and a `ccpkg` wrapper that sets
`CCPKG_ROOT`. Apply it to your `~/.claude` (and re-apply after each `brew upgrade ccpkg`):

```sh
ccpkg install   # interactive feature picker, or
ccpkg pull      # apply the saved/default selection headlessly
```

`ccpkg push` (capturing live edits back into the repo) is disabled in a Homebrew install —
it needs a git checkout, so use the from-source path below for that workflow.

### From source (for development)

Clone the repo and run the bootstrap script, which ensures `git`, `python3`, and `jq` are
present (via `brew`/`apt`) and then runs `python3 -m ccpkg install`:

```sh
git clone https://github.com/aahilshaikh-twlbs/ccpkg
cd ccpkg
cp local.env.example local.env   # edit per-machine values (optional)
./install.sh
```

For a step-by-step, verifiable walkthrough, see [SETUP.md](./SETUP.md). For how Claude Code
itself reconstructs the environment, see [CLAUDE.md](./CLAUDE.md).

## Quick start

`ccpkg install` runs a fresh-machine bootstrap: it loads per-machine config, ensures OS
dependencies, applies the base layer (and a private overlay if one is configured), reinstalls
plugins, installs the mailbox, scans for secrets/PII, and prints any re-auth instructions. It
is idempotent — re-running it converges to the same state.

Run in a terminal, `ccpkg install` opens an interactive feature picker before applying
anything. Features are grouped into screens (Core, Commands, Skills, Plugins, Coordination,
Hooks, and an Overlay group when an overlay is configured). Use ↑/↓ to move, space to toggle,
Enter to advance, ←/→ to move between groups, and Esc to go back; Esc on the welcome screen
cancels. Your selection is saved to `~/.claude/.ccpkg-profile.json`.

**Re-running `ccpkg install` is how you update** — it reopens the picker pre-ticked from your
saved selection, so you can add or remove features. No flag needed.

```text
ccpkg install                # interactive picker (pre-filled on a re-run)
ccpkg install --yes          # headless: apply saved profile or defaults, no prompts
ccpkg uninstall              # remove managed files, restore backups, drop mailbox + profile
```

`--yes` (alias `--non-interactive`) is fully headless — it applies the saved profile, or the
defaults if none exists, with no prompts. `install.sh` uses it so the bootstrap never blocks.
`ccpkg uninstall` asks to confirm first (or pass `--yes`); it never deletes `settings.json`
outright — it restores the pre-install backup, or leaves the file for manual review.

## How it works

### Base and overlay layers

The setup is split into two layers so the public repo stays clean and shareable:

- **Base — this repo.** Fully scrubbed: no PII, no company-specifics, no secrets. The base
  alone yields a complete, generic environment. It is the source of truth for portable
  customization.
- **Overlay — a separate private repo or directory.** Same `home/.claude/` mirror structure,
  holding only personal or company content (your own agents, internal skills, allowlist
  entries, and so on). It layers on top of the base, adding new files and merging extra
  `settings`/allowlist entries.

Point ccpkg at your own overlay in `local.env` (both optional):

- `OVERLAY_REPO=<git url>` — a private overlay repo the installer clones and applies; or
- `OVERLAY_DIR=<path>` — a local overlay directory.

If neither is set, only the base applies and the system is fully functional (just generic).
`ccpkg install` always applies **base, then overlay (if present)** using the same machinery.

See [`docs/overlay-example/`](docs/overlay-example/) for the exact overlay layout (its own
`manifest.json` with `layer="overlay"` items plus a `home/.claude/` mirror).

### Sync model

Each managed item declares a `mode` in `manifest.json`:

- **`symlink`** — OS/path-agnostic hand-authored content (statusline, cost scripts, commands,
  generic skills). The repo file *is* the live file.
- **`template`** — files containing `${VAR}` machine values. Copied with substitution and
  regenerated on `pull`.
- **`merge`** — Claude-managed JSON (`settings.json`). Deep-merged into the live file
  (base-managed keys win, live-only keys preserved), so Claude Code can still rewrite it live;
  reconciled via `push`.

### Secrets and portability

- Credentials never enter git (either layer). A fresh machine re-authenticates with
  `claude auth login` (or a credential token in the environment). See [SETUP.md](./SETUP.md)
  Step 7.
- Cross-platform by construction: `$HOME`/`~` where the shell expands, `${VAR}` templating for
  the rest, and an OS-aware installer (`brew`/`apt`, BSD/GNU `stat`).
- Every apply backs up before overwrite (`*.ccpkg.bak`) and is idempotent.

### Scope

Supports macOS and Ubuntu. Does not sync machine state/history, does not store encrypted
secrets in git (it excludes them and re-auths instead), and does not auto-publish or manage
the repo's GitHub remote.

## Commands

`ccpkg <command>` (equivalently `python3 -m ccpkg <command>` from a checkout; no third-party
dependencies):

| Command | What it does |
| --- | --- |
| `install` | Bootstrap / update (idempotent): deps, base, overlay, plugins, mailbox, scan, re-auth notes. Interactive runs open the picker (pre-filled on a re-run); `--yes` is headless. |
| `pull` | Re-apply repo to live `~/.claude` (symlink/template/merge; backs up first). |
| `push [paths...]` | Capture changed live files into the right layer; reverse-templatize machine values; secret-scan. No auto-commit. Requires a git checkout. |
| `uninstall` | Remove managed files from `~/.claude` (restoring `*.ccpkg.bak` backups), drop the mailbox runtime + saved profile. Confirms first; `--yes` to skip. Never deletes `settings.json` outright. |
| `status` | Per-file drift between the repo and live `~/.claude`. |
| `doctor` | Environment health report: deps, profile, mailbox state, and a drift summary. |
| `scan` | Secrets + base-purity scan; exits non-zero on findings. Also the pre-commit hook. |

## Repository layout

```
ccpkg/
  CLAUDE.md            # Claude reads this first: "to reconstruct, run ./install.sh OR follow SETUP.md"
  SETUP.md             # ordered, verifiable reconstruction playbook
  README.md            # this file
  install.sh           # bash bootstrap -> python3 -m ccpkg install
  local.env.example    # per-machine variables template
  manifest.json        # declarative managed-set: path, mode, os, layer
  home/.claude/        # source-of-truth mirror of the portable (base) setup
  mailbox/             # vendored mailbox coordinator ($HOME-relative hooks)
  ccpkg/               # Python installer/CLI (stdlib only, python3 >= 3.9)
  Formula/ccpkg.rb     # Homebrew formula
  .githooks/pre-commit # runs `ccpkg scan`; blocks commits with secrets/PII
```

## Contributing

### Adding a feature

1. Add the file under `home/.claude/` (base) or your overlay's mirror.
2. Add a matching entry to `manifest.json`:

   ```json
   {
     "items": [
       { "path": "commands/my-command.md", "mode": "symlink", "os": "any", "layer": "base" }
     ]
   }
   ```

   Choose `mode` (`symlink` | `template` | `merge`), `os` (`any` | `darwin` | `linux`), and
   `layer` (`base` for generic/shareable, `overlay` for personal/company).
3. Run the scan and apply, then commit (base) or push to your overlay:

   ```sh
   python3 -m ccpkg scan
   python3 -m ccpkg pull
   git add -A && git commit -m "feat: add my-command"
   ```

   The pre-commit hook re-runs `ccpkg scan` and blocks the commit if it finds secrets or
   base-purity (PII/company) content — move such content to an overlay or templatize it with
   `${VAR}`.

### Running from a package (`CCPKG_ROOT`)

ccpkg also runs from a read-only, git-less install (such as the Homebrew package). A packaged
install sets:

| Variable | Meaning |
|----------|---------|
| `CCPKG_ROOT` | absolute path to the bundled asset tree (`manifest.json`, `home/.claude/`, `mailbox/`). When set, ccpkg reads its assets from here instead of a git checkout. |
| `CCPKG_LOCAL_ENV` | optional explicit path to `local.env`. |

When `CCPKG_ROOT` is set, ccpkg:

- reads `local.env` from `$CCPKG_LOCAL_ENV` → `~/.config/ccpkg/local.env` (honoring
  `$XDG_CONFIG_HOME`) → `<root>/local.env`, using the first that exists;
- **skips runtime dependency installation** (`git`/`python3`/`jq` are declared package
  dependencies, not installed on the fly); and
- disables `ccpkg push` (capturing live edits back into the repo needs a git checkout — it
  exits non-zero with a message pointing you at a clone for the dev workflow).

A plain git checkout running `python3 -m ccpkg` is unaffected: with `CCPKG_ROOT` unset, assets
resolve relative to the checkout and `local.env` falls back to `<repo>/local.env`. `make dist`
builds the versioned tarball (`ccpkg --version`) that the package definitions consume; see
[RELEASING.md](./RELEASING.md) for cutting new versions.

## License

MIT. See [LICENSE](./LICENSE).
