# Overlay example (sample, committed)

This directory is a **committed, scrubbed example** of the private-overlay layout. It is
NOT your real overlay and is never applied automatically by `ccpkg install`. It exists so
you can see the exact shape an overlay must have.

## Structure (mirrors the base)

An overlay has the **same `home/.claude/` mirror** as the public base, plus **its own
`manifest.json`** whose every item declares `"layer": "overlay"`:

```
<your-overlay>/
  manifest.json                 # items, each with "layer": "overlay"
  home/.claude/
    agents/...                  # your personal <name>-* agents (PRIVATE)
    skills/<company-skill>/...   # company-specific skill (PRIVATE)
    settings.local.json.tmpl    # AWS allowlist + abs paths as ${VAR} (template)
```

Each manifest item's `path` names the real file on disk; templated files keep their
`.tmpl` suffix in both the manifest `path` and on disk, and `ccpkg` strips that suffix
from the live target when it renders them.

## Where the REAL overlay lives

The real overlay is a **separate private location**, configured in your gitignored
`local.env` (both optional; if neither is set, only the generic public base applies):

- `OVERLAY_REPO=<git url>` — a private repo `ccpkg` clones into `~/.cache/ccpkg/overlay`
  (`installer.clone_overlay`), then applies.
- `OVERLAY_DIR=<path>` — a local directory applied in place.

`ccpkg install` applies **base first, then overlay** with the same machinery
(`apply.apply_layer(..., layer="overlay", ...)`), so overlay files add new files and
layer templated allowlist entries on top of the base.

## What goes in the overlay vs the base

- **Overlay (PRIVATE, never committed to this base repo):** your personal `<name>-*`
  agents, company-specific skills, AWS profile / absolute-path allowlist entries, vault
  wiring.
- **Base (PUBLIC, this repo):** only generic, scrubbed, PII-free content.

Overlay files are exempt from the base-purity scan; base files are NOT (`scan.scan_paths`
runs purity only when `layer == "base"`). That is why company/personal content must live
here in the overlay layer.

## Migrating your real content (LOCAL action — do NOT commit to base)

This is something **you** do on your own machine; it is intentionally not automated by
this task and produces nothing in the public base repo:

1. Create your private overlay (a private git repo or a local dir), copying this
   example's layout: a `manifest.json` (items `"layer": "overlay"`) plus `home/.claude/`.
2. Move your personal `<name>-*` agents and any company-specific skills into the
   overlay's `home/.claude/`; add one overlay manifest item per file (use
   `"mode": "template"` for any file containing `${VAR}` tokens).
3. Set `OVERLAY_REPO` or `OVERLAY_DIR` in your `local.env`.
4. Run `python3 -m ccpkg install` (or `pull`) — base applies, then your overlay applies
   on top.
