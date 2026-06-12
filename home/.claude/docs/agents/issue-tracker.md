# Issue tracker: GitHub (global default)

GLOBAL DEFAULT for Matt Pocock's engineering skills (`to-issues`, `triage`, `qa`,
`to-prd`). Applies to whatever repo you're working in. A repo with its own
`docs/agents/issue-tracker.md` overrides this.

Issues and PRDs live as GitHub issues for the current repo. Use the `gh` CLI for all
operations; `gh` infers the repo from `git remote -v` when run inside a clone.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."` (heredoc for multi-line bodies).
- **Read an issue**: `gh issue view <number> --comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with `--label` / `--state` filters.
- **Comment**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

If the current directory isn't a GitHub clone (no `gh`-resolvable remote), say so and ask
where to file instead — don't invent a tracker.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
