# graphify
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.

## Agent skills

GLOBAL defaults for Matt Pocock's engineering skills (`to-issues`, `triage`, `qa`, `to-prd`, `tdd`, `diagnose`, `review`, `improve-codebase-architecture`, `grill-with-docs`), applied to whatever repo you're working in. Per-repo config wins: if a repo has its own `docs/agents/*.md` or its own `## Agent skills` block, follow that instead.

### Issue tracker
GitHub via the `gh` CLI, against the current repo's `origin`. See `~/.claude/docs/agents/issue-tracker.md`.

### Triage labels
Canonical defaults: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `~/.claude/docs/agents/triage-labels.md`.

### Domain docs
Single-context: read `CONTEXT.md` + `docs/adr/` in the current repo if present; proceed silently if absent. See `~/.claude/docs/agents/domain.md`.
