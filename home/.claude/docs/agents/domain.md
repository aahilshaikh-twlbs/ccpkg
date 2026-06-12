# Domain docs (global default)

How the engineering skills (`improve-codebase-architecture`, `diagnose`, `tdd`,
`grill-with-docs`) consume a repo's domain documentation. GLOBAL DEFAULT — single-context
posture. A repo with its own `docs/agents/domain.md`, or a root `CONTEXT-MAP.md`
(multi-context), overrides this.

## Before exploring, read these in the current repo (if present)

- **`CONTEXT.md`** at the repo root, or
- **`CONTEXT-MAP.md`** at the root if it exists — it points at one `CONTEXT.md` per
  context. Read each one relevant to the topic.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in. In
  multi-context repos, also check `src/<context>/docs/adr/` for context-scoped decisions.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't
suggest creating them upfront. The producer skill (`/grill-with-docs`) creates them lazily
when terms or decisions actually get resolved.

## Use the glossary's vocabulary

When your output names a domain concept (issue title, refactor proposal, hypothesis, test
name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary
avoids. If the concept isn't in the glossary yet, that's a signal — either you're
inventing language the project doesn't use (reconsider) or there's a real gap (note it for
`/grill-with-docs`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently
overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
