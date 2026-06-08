from ccpkg.swarm import prompts


def test_kickoff_substitutes_all_tokens():
    text = prompts.kickoff(
        swarm_id="abc123",
        lead="lead-1",
        sibling_leads=["lead-2", "lead-3"],
        swarm_board="swarm-abc123",
    )
    assert "abc123" in text
    assert "lead-1" in text
    assert "lead-2" in text and "lead-3" in text
    assert "swarm-abc123" in text
    assert "$SWARM_WORKDIR/result.md" in text or "${SWARM_WORKDIR}/result.md" in text


def test_kickoff_contains_recursion_ban():
    text = prompts.kickoff("abc", "lead-1", [], "swarm-abc")
    assert "NOT" in text.upper() and "swarm" in text.lower()
    # Explicit ban string we'll always include
    assert "do NOT call /swarm" in text


def test_kickoff_sibling_list_with_no_siblings():
    text = prompts.kickoff("abc", "lead-1", [], "swarm-abc")
    # Should not crash; should render some sensible "no siblings" form
    assert "lead-1" in text


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
