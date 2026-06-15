"""Curated MCP-server catalog + project-scope .mcp.json apply (§2 adoption features).

`ccpkg mcp list` shows the catalog; `ccpkg mcp add <name...>` deep-merges the named
servers into ./.mcp.json (PROJECT scope — deliberately never ~/.claude.json, which
is Claude Code's own mutable state file), preserving any servers already present.

Secrets never live in the file: credentials are `${VAR}` references that Claude Code
expands from the environment at connect time, so the catalog (and this module) is
base-pure. Server entries that need a token store the env-var NAME in `env_vars`;
the `env` block is built at runtime, which also keeps token-shaped names (e.g.
GITHUB_PERSONAL_ACCESS_TOKEN) out of this source file's literals.

Stdlib only, Python 3.9.
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

MCP_FILENAME = ".mcp.json"

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class MCPServer:
    id: str
    desc: str
    transport: str                              # "stdio" | "http" | "sse"
    command: str = ""                           # stdio
    args: tuple = field(default_factory=tuple)  # stdio (may hold ${VAR} placeholders)
    url: str = ""                               # http | sse
    env_vars: tuple = field(default_factory=tuple)  # env-block ${VAR} names

    def entry(self):
        # type: () -> dict
        """The object stored under mcpServers[<id>] in .mcp.json."""
        if self.transport == "stdio":
            out = {"command": self.command, "args": list(self.args)}
            if self.env_vars:
                out["env"] = {name: "${" + name + "}" for name in self.env_vars}
            return out
        return {"type": self.transport, "url": self.url}

    def referenced_vars(self):
        # type: () -> List[str]
        """Every ${VAR} the user must set for this server (env block + args)."""
        return sorted(set(_VAR_RE.findall(json.dumps(self.entry()))))


# Curated catalog. HTTP servers are official hosted endpoints (OAuth in-client,
# no header needed). stdio servers run via npx; token-bearing ones name their
# env var in env_vars; path-shaped inputs are ${VAR} placeholders in args.
MCP_CATALOG = [
    MCPServer("github", "GitHub repos, issues, PRs, commits", "stdio",
              command="npx", args=("-y", "@modelcontextprotocol/server-github"),
              env_vars=("GITHUB_PERSONAL_ACCESS_TOKEN",)),
    MCPServer("firecrawl", "Web scraping + markdown extraction", "stdio",
              command="npx", args=("-y", "firecrawl-mcp"),
              env_vars=("FIRECRAWL_API_KEY",)),
    MCPServer("brave-search", "Real-time web search", "stdio",
              command="npx", args=("-y", "@modelcontextprotocol/server-brave-search"),
              env_vars=("BRAVE_API_KEY",)),
    MCPServer("playwright", "Browser automation, screenshots, E2E", "stdio",
              command="npx", args=("-y", "@modelcontextprotocol/server-playwright")),
    MCPServer("filesystem", "Local file read/write under a chosen root", "stdio",
              command="npx",
              args=("-y", "@modelcontextprotocol/server-filesystem", "${MCP_FS_ROOT}")),
    MCPServer("git", "Local git repo inspection (log, diff, blame)", "stdio",
              command="npx", args=("-y", "@modelcontextprotocol/server-git")),
    MCPServer("sqlite", "Query a local SQLite database", "stdio",
              command="npx",
              args=("-y", "@modelcontextprotocol/server-sqlite", "${MCP_SQLITE_DB}")),
    MCPServer("postgres", "Live SQL against a Postgres database", "stdio",
              command="npx",
              args=("-y", "@modelcontextprotocol/server-postgres",
                    "${POSTGRES_CONNECTION_STRING}")),
    MCPServer("slack", "Slack channels, threads, search, post", "http",
              url="https://mcp.slack.com/mcp"),
    MCPServer("linear", "Linear issues, cycles, project updates", "http",
              url="https://mcp.linear.app/mcp"),
    MCPServer("vercel", "Vercel deployments, builds, previews", "http",
              url="https://mcp.vercel.com"),
    MCPServer("stripe", "Stripe payments, customers, invoices", "http",
              url="https://mcp.stripe.com"),
    MCPServer("notion", "Notion search + page read/write", "http",
              url="https://mcp.notion.com/mcp"),
    MCPServer("google-drive", "Google Drive file search, read, upload", "http",
              url="https://drivemcp.googleapis.com/mcp/v1"),
]


def by_id():
    # type: () -> Dict[str, MCPServer]
    return {s.id: s for s in MCP_CATALOG}


def catalog_ids():
    # type: () -> List[str]
    return [s.id for s in MCP_CATALOG]


def mcp_json_path(cwd=None):
    # type: (Optional[str]) -> str
    return os.path.join(cwd or os.getcwd(), MCP_FILENAME)


def load(path):
    # type: (str) -> dict
    """Parse an existing .mcp.json, or {} if absent/unreadable/not an object."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def present_ids(path):
    # type: (str) -> set
    """Server names already configured in the .mcp.json at `path`."""
    servers = load(path).get("mcpServers")
    return set(servers.keys()) if isinstance(servers, dict) else set()


def _write_json(path, doc):
    # type: (str, dict) -> None
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def apply_servers(ids, path):
    # type: (List[str], str) -> dict
    """Deep-merge the named catalog servers into mcpServers in the .mcp.json at
    `path`, preserving existing servers. Idempotent. Returns a result dict with
    added / updated / present id lists, the env vars to set, and the path."""
    doc = load(path)
    servers = doc.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    catalog = by_id()
    added, updated, present = [], [], []
    for sid in ids:
        entry = catalog[sid].entry()
        if sid not in servers:
            added.append(sid)
        elif servers[sid] != entry:
            updated.append(sid)
        else:
            present.append(sid)
        servers[sid] = entry
    doc["mcpServers"] = servers
    _write_json(path, doc)
    vars_ = sorted({v for sid in ids for v in catalog[sid].referenced_vars()})
    return {"path": path, "added": added, "updated": updated,
            "present": present, "vars": vars_}
