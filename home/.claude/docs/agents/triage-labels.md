# Triage labels (global default)

GLOBAL DEFAULT for the `triage` skill. The five canonical roles map 1:1 to these label
strings. A repo with its own `docs/agents/triage-labels.md` overrides this.

| Role in mattpocock/skills | Label string | Meaning                                  |
| ------------------------- | ------------ | ---------------------------------------- |
| `needs-triage`            | `needs-triage`    | Maintainer needs to evaluate        |
| `needs-info`              | `needs-info`      | Waiting on reporter for more info   |
| `ready-for-agent`         | `ready-for-agent` | Fully specified, ready for an AFK agent |
| `ready-for-human`         | `ready-for-human` | Requires human implementation       |
| `wontfix`                 | `wontfix`         | Will not be actioned                |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the label
string from this table. If a repo already uses different label names, create a per-repo
`docs/agents/triage-labels.md` override rather than editing this global file.
