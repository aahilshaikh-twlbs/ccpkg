from ccpkg.swarm import prompts


def test_kickoff_is_single_line():
    """Probe 2 finding: write text sends each embedded newline as a submit, so a
    multi-line kickoff would fire partial prompts. The kickoff must be one line;
    all detail lives in inbox.md (which the lead reads)."""
    text = prompts.kickoff("abc123", "lead-1",
                           "/tmp/ccpkg-swarm/abc123/lead-1/inbox.md")
    assert "\n" not in text.strip()


def test_kickoff_points_at_inbox_path():
    path = "/tmp/ccpkg-swarm/abc123/lead-1/inbox.md"
    text = prompts.kickoff("abc123", "lead-1", path)
    assert path in text
    assert "abc123" in text
    assert "lead-1" in text


def test_kickoff_contains_recursion_ban():
    text = prompts.kickoff("abc", "lead-1", "/tmp/x/inbox.md")
    assert "do NOT call /swarm" in text


def test_inbox_body_includes_subtask_and_coord_section():
    body = prompts.inbox_body(
        swarm_id="abc",
        lead="lead-1",
        sibling_leads=["lead-2"],
        subtask="refactor wizard.py to extract layout helpers",
    )
    assert body.startswith("---")  # frontmatter
    assert "swarm_id: abc" in body
    assert "lead: lead-1" in body
    assert "refactor wizard.py" in body
    assert "Coordination" in body
    assert "Done signal" in body


def test_inbox_done_signal_uses_absolute_mailbox_path_and_no_board_flag():
    """Lead-side mailbox defects: `mailbox` is not on PATH (only
    ~/.claude/mailbox/mailbox), and `mailbox send` has no --board flag (routing
    is implicit via the joined primary board)."""
    body = prompts.inbox_body("abc", "lead-1", [], "do the thing")
    assert "~/.claude/mailbox/mailbox send" in body
    assert "--board" not in body
    assert "--kind swarm_done" in body
    # result path still wired through the lead's workdir env
    assert "$SWARM_WORKDIR" in body


def test_inbox_body_no_siblings_renders_cleanly():
    body = prompts.inbox_body("abc", "lead-1", [], "x")
    assert "sibling_leads: []" in body
