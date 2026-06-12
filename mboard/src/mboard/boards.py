import hashlib
import os
import re
import subprocess
from typing import Tuple


def derive_repo_board(cwd: str) -> Tuple[str, str]:
    """Derive the auto repo board id and its origin path for a working dir.

    Tries `git -C <cwd> rev-parse --show-toplevel` (the working-tree root, NOT
    --git-common-dir, so worktrees are distinct boards). On success returns
    ("repo-" + sha1(toplevel)[:12], toplevel). On any failure (not a repo,
    git missing, timeout, empty output) falls back to
    ("cwd-" + sha1(cwd)[:12], cwd).
    """
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2,
        )
        if proc.returncode == 0:
            toplevel = proc.stdout.decode("utf-8", "replace").strip()
            if toplevel:
                board_id = "repo-" + hashlib.sha1(toplevel.encode()).hexdigest()[:12]
                return (board_id, toplevel)
    except (OSError, subprocess.SubprocessError):
        pass

    root = os.path.realpath(cwd)
    board_id = "cwd-" + hashlib.sha1(root.encode()).hexdigest()[:12]
    return (board_id, root)


def board_id_for_name(name: str) -> str:
    """Map a human board name to a stable id: "named-" + slug.

    Slug: lowercase, every run of non-[a-z0-9] chars -> "-", strip leading/
    trailing "-", capped at 40 chars.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
    return "named-" + slug
