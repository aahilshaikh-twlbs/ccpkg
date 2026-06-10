"""ccpkg.scaffold — scaffold a new managed item (file + manifest entry).

`ccpkg new <kind> <name>` writes a starter file under
<root>/home/.claude/<relpath> and inserts a one-line manifest entry into
<root>/manifest.json (text insertion, to preserve the compact
one-object-per-line formatting). Stdlib-only.
"""

import os
import re

from . import manifest

# kind: (rel_path_template, group, default, mode)
KINDS = {
    "agent":   ("agents/{name}.md",       "Agents",   False, "symlink"),
    "command": ("commands/{name}.md",     "Commands", True,  "symlink"),
    "skill":   ("skills/{name}/SKILL.md", "Skills",   True,  "symlink"),
    "hook":    ("hooks/{name}.py",        "Hooks",    True,  "symlink"),
}

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _agent_template(name):
    # type: (str) -> str
    return (
        "---\n"
        "name: {name}\n"
        "description: TODO one-line description\n"
        "tools: Read, Grep, Glob\n"
        "model: sonnet\n"
        "---\n"
        "\n"
        "You are {name}. TODO: one-line statement of this agent's role.\n"
        "\n"
        "## Method\n"
        "\n"
        "1. TODO: first step.\n"
    ).format(name=name)


def _command_template(name):
    # type: (str) -> str
    return (
        "---\n"
        "description: TODO\n"
        "---\n"
        "\n"
        "# /{name}\n"
        "\n"
        "TODO: describe what `/{name}` does and how to use it.\n"
    ).format(name=name)


def _skill_template(name):
    # type: (str) -> str
    return (
        "---\n"
        "name: {name}\n"
        "description: TODO (must explain when to use)\n"
        "---\n"
        "\n"
        "# {name}\n"
        "\n"
        "TODO: describe the skill's workflow.\n"
    ).format(name=name)


def _hook_template(name):
    # type: (str) -> str
    return (
        "#!/usr/bin/env python3\n"
        '"""{name} hook: a no-op Claude Code hook.\n'
        "\n"
        "Reads the hook JSON payload on stdin and exits 0 without acting.\n"
        "TODO: implement the hook behavior.\n"
        '"""\n'
        "import json\n"
        "import sys\n"
        "\n"
        "\n"
        "def main():\n"
        "    # type: () -> int\n"
        "    try:\n"
        "        json.load(sys.stdin)\n"
        "    except Exception:\n"
        "        pass\n"
        "    return 0\n"
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    sys.exit(main())\n"
    ).format(name=name)


_TEMPLATES = {
    "agent": _agent_template,
    "command": _command_template,
    "skill": _skill_template,
    "hook": _hook_template,
}


def _insert_manifest_line(manifest_file, line):
    # type: (str, str) -> None
    """Insert `line` as a new item just before the closing `]` of the items
    array, ensuring the previous item line gets a trailing comma. Text-only;
    preserves the existing one-object-per-line formatting."""
    with open(manifest_file, "r", encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    # Find the closing bracket of the items array (last line that is just `]`,
    # ignoring trailing whitespace), scanning from the end.
    close_idx = None
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].strip() == "]":
            close_idx = idx
            break
    if close_idx is None:
        raise ValueError("could not locate items array closing ']' in manifest")

    # Indentation for the new item: match the line above the bracket if it is an
    # item, else default to two levels (4 spaces) under the bracket's indent.
    bracket_indent = lines[close_idx][: len(lines[close_idx]) - len(lines[close_idx].lstrip())]

    # Find the last non-blank line before the bracket (the last existing item).
    prev_idx = None
    for idx in range(close_idx - 1, -1, -1):
        if lines[idx].strip():
            prev_idx = idx
            break

    if prev_idx is not None and lines[prev_idx].strip().startswith("{"):
        item_indent = lines[prev_idx][: len(lines[prev_idx]) - len(lines[prev_idx].lstrip())]
        # Ensure the preceding item line ends with a comma.
        if not lines[prev_idx].rstrip().endswith(","):
            lines[prev_idx] = lines[prev_idx].rstrip() + ","
    else:
        item_indent = bracket_indent + "  "

    new_line = item_indent + line
    lines.insert(close_idx, new_line)

    with open(manifest_file, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def create(root, kind, name, group=None, default=None):
    # type: (str, str, str, object, object) -> list
    """Scaffold a new managed item: write a starter file under
    <root>/home/.claude/<relpath> AND insert a manifest entry in
    <root>/manifest.json. Returns [file_path, "manifest.json"].

    Raises ValueError on unknown kind, invalid name (must match
    ^[a-z0-9][a-z0-9-]*$), existing file, or duplicate manifest path."""
    if kind not in KINDS:
        raise ValueError(
            "unknown kind %r; expected one of %s" % (kind, tuple(sorted(KINDS)))
        )
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError(
            "invalid name %r; must match ^[a-z0-9][a-z0-9-]*$" % (name,)
        )

    rel_template, default_group, default_default, mode = KINDS[kind]
    rel_path = rel_template.format(name=name)

    # The manifest path: the registered path. For skills this is the directory
    # (skills/{name}), even though the file written is skills/{name}/SKILL.md.
    if kind == "skill":
        manifest_rel = "skills/{name}".format(name=name)
    else:
        manifest_rel = rel_path

    file_path = os.path.join(root, "home", ".claude", *rel_path.split("/"))
    manifest_file = os.path.join(root, "manifest.json")

    if os.path.exists(file_path):
        raise ValueError("target file already exists: %s" % file_path)

    # Refuse a duplicate manifest path.
    for item in manifest.parse(manifest_file):
        if item.path == manifest_rel:
            raise ValueError(
                "manifest already has an item with path %r" % manifest_rel
            )

    eff_group = group if group else default_group
    eff_default = default_default if default is None else bool(default)

    # Write the starter file.
    parent = os.path.dirname(file_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(_TEMPLATES[kind](name))

    # Build and insert the manifest line (single line, compact style).
    line = (
        '{{"path": "{path}", "mode": "{mode}", "os": "any", '
        '"layer": "base", "group": "{group}", '
        '"desc": "TODO: describe {name}", "default": {default}}}'
    ).format(
        path=manifest_rel,
        mode=mode,
        group=eff_group,
        name=name,
        default="true" if eff_default else "false",
    )
    _insert_manifest_line(manifest_file, line)

    return [file_path, "manifest.json"]
