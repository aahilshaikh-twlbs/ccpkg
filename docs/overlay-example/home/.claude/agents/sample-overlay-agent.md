---
name: sample-overlay-agent
description: Example overlay-only agent. Replace with your real private agent in YOUR overlay repo/dir.
---

# Sample Overlay Agent

This agent lives in the **private overlay**, not in the public base. It exists only to
demonstrate the overlay layout and templating. Copy this shape into your own
`OVERLAY_DIR`/`OVERLAY_REPO`; do NOT commit real personal agents into the base repo.

## On-demand reference

<!-- ccpkg:vault:start -->
Reference docs root: ${VAULT_ROOT}
<!-- ccpkg:vault:end -->

When `VAULT_ROOT` is unset, `ccpkg` strips the block above so the agent never points at a
dead path. When set, `${VAULT_ROOT}` is substituted with the per-machine value.
