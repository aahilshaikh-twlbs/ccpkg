"""Tests for MailboxEngine messaging: send / poll_inbox / request_release."""


def _join(engine, session_id, label, cwd, board_name=None):
    """Helper: join a session and return the join result dict."""
    return engine.join(
        session_id=session_id,
        label=label,
        cwd=cwd,
        board_name=board_name,
    )


def test_send_returns_id_and_stores_message(engine, tmp_path):
    _join(engine, "sess_a", "alice", str(tmp_path), board_name="proj")
    result = engine.send(
        session_id="sess_a",
        to="*",
        kind="note",
        body="hello board",
    )
    assert "id" in result
    assert result["id"].startswith("msg_")
    stored = engine.messages[result["id"]]
    assert stored.from_session == "sess_a"
    assert stored.from_label == "alice"
    assert stored.to == "*"
    assert stored.kind == "note"
    assert stored.body == "hello board"
    assert stored.ref_paths == []
    # primary board is the named board when one was joined
    assert stored.board == engine._primary_board("sess_a")


def test_broadcast_delivered_to_coboard_session_not_sender(engine, tmp_path):
    _join(engine, "sess_a", "alice", str(tmp_path), board_name="proj")
    _join(engine, "sess_b", "bob", str(tmp_path), board_name="proj")
    engine.send(session_id="sess_a", to="*", kind="note", body="hi all")

    inbox_b = engine.poll_inbox("sess_b")
    bodies_b = [m["body"] for m in inbox_b if m["from_session"] == "sess_a" and m["kind"] == "note"]
    assert "hi all" in bodies_b

    inbox_a = engine.poll_inbox("sess_a")
    bodies_a = [m["body"] for m in inbox_a]
    assert "hi all" not in bodies_a


def test_directed_delivery_by_label(engine, tmp_path):
    _join(engine, "sess_a", "alice", str(tmp_path), board_name="proj")
    _join(engine, "sess_b", "bob", str(tmp_path), board_name="proj")
    _join(engine, "sess_c", "carol", str(tmp_path), board_name="proj")
    engine.send(session_id="sess_a", to="bob", kind="note", body="for bob only")

    inbox_b = engine.poll_inbox("sess_b")
    assert any(m["body"] == "for bob only" for m in inbox_b)

    inbox_c = engine.poll_inbox("sess_c")
    assert all(m["body"] != "for bob only" for m in inbox_c)

    inbox_a = engine.poll_inbox("sess_a")
    assert all(m["body"] != "for bob only" for m in inbox_a)


def test_read_receipt_prevents_redelivery(engine, tmp_path):
    _join(engine, "sess_a", "alice", str(tmp_path), board_name="proj")
    _join(engine, "sess_b", "bob", str(tmp_path), board_name="proj")
    msg_id = engine.send(session_id="sess_a", to="bob", kind="note", body="once")["id"]

    first = engine.poll_inbox("sess_b")
    assert any(m["id"] == msg_id for m in first)
    # read_by now records the recipient
    assert "sess_b" in engine.messages[msg_id].read_by

    second = engine.poll_inbox("sess_b")
    assert all(m["id"] != msg_id for m in second)


def test_join_colocation_broadcast_reaches_coboard_not_joiner(engine, tmp_path):
    _join(engine, "sess_a", "alice", str(tmp_path), board_name="proj")
    # sess_b joining triggers join() to queue a co-location note (sess_a is live).
    _join(engine, "sess_b", "bob", str(tmp_path), board_name="proj")

    # The already-present co-board session receives the join broadcast.
    inbox_a = engine.poll_inbox("sess_a")
    notes_from_b = [m for m in inbox_a if m["from_session"] == "sess_b" and m["kind"] == "note"]
    assert len(notes_from_b) >= 1
    assert all(m["to"] == "*" for m in notes_from_b)

    # The joiner never receives its own co-location broadcast.
    inbox_b = engine.poll_inbox("sess_b")
    assert all(m["from_session"] != "sess_b" for m in inbox_b)


def test_request_release_no_holder_returns_error(engine, tmp_path):
    _join(engine, "sess_a", "alice", str(tmp_path), board_name="proj")
    target = str(tmp_path / "src" / "untouched.py")
    result = engine.request_release(session_id="sess_a", abs_path=target)
    assert result == {"error": "no-holder"}


def test_request_release_with_holder_queues_message(engine, tmp_path):
    _join(engine, "sess_a", "alice", str(tmp_path))
    _join(engine, "sess_b", "bob", str(tmp_path))
    target = str(tmp_path / "src" / "core.py")
    engine.claim(session_id="sess_b", globs=[target], note="refactor")

    result = engine.request_release(session_id="sess_a", abs_path=target)
    assert result == {"sent_to": "bob"}

    inbox_b = engine.poll_inbox("sess_b")
    reqs = [m for m in inbox_b if m["kind"] == "release-request"]
    assert len(reqs) == 1
    assert reqs[0]["from_session"] == "sess_a"
    assert reqs[0]["to"] == "bob"
    assert target in reqs[0]["body"]
    assert reqs[0]["ref_paths"] == [target]
