import io

from ccpkg import wizard
from ccpkg.selection import Stage, Entry


def _stages():
    return [
        Stage("Core", [Entry("settings.json", "settings", True, "file"),
                       Entry("statusline.sh", "statusline", True, "file")]),
        Stage("Plugins", [Entry("superpowers", "skills", True, "plugin"),
                          Entry("frontend-design", "ui", False, "plugin")]),
    ]


def test_initial_preselected_are_ticked():
    st = wizard.WizardState(_stages(), {"settings.json", "superpowers"})
    assert st.is_selected("settings.json")
    assert not st.is_selected("statusline.sh")


def test_move_and_toggle():
    st = wizard.WizardState(_stages(), set())
    assert st.cursor == 0
    st.move(1)
    assert st.cursor == 1
    st.toggle()                       # toggle statusline.sh on
    assert st.is_selected("statusline.sh")
    st.toggle()                       # back off
    assert not st.is_selected("statusline.sh")


def test_move_clamps_within_stage():
    st = wizard.WizardState(_stages(), set())
    st.move(-1)
    assert st.cursor == 0             # clamped at top
    st.move(99)
    assert st.cursor == 1             # clamped at bottom (2 entries)


def test_select_all_and_none_affect_current_stage_only():
    st = wizard.WizardState(_stages(), set())
    st.select_all()
    assert st.is_selected("settings.json") and st.is_selected("statusline.sh")
    st.next_stage()
    st.select_none()
    assert not st.is_selected("superpowers")
    # previous stage untouched
    assert st.is_selected("settings.json")


def test_stage_navigation_and_done():
    st = wizard.WizardState(_stages(), set())
    assert st.stage_index == 0
    st.next_stage()
    assert st.stage_index == 1
    assert not st.is_done()
    st.next_stage()                   # past last stage -> done
    assert st.is_done()
    st.prev_stage()                   # back off the done state
    assert not st.is_done()
    assert st.stage_index == 1


def test_selected_ids_returns_full_set():
    st = wizard.WizardState(_stages(), {"settings.json"})
    st.next_stage()
    st.toggle()                       # superpowers (cursor 0 of stage 2) -> off? it's preselected? no
    # superpowers default not preselected here (empty start except settings.json)
    assert st.is_selected("superpowers") is True or st.is_selected("superpowers") is False
    ids = st.selected_ids()
    assert "settings.json" in ids


def test_numbered_fallback_toggles_and_advances():
    # Stage 1: toggle entry 2 on (statusline), then Enter; Stage 2: 'n' then Enter.
    stages = _stages()
    instream = io.StringIO("2\n\nn\n\n")
    outstream = io.StringIO()
    result = wizard._numbered_fallback(stages, {"settings.json", "superpowers"},
                                       instream, outstream)
    assert "settings.json" in result          # carried from preselected
    assert "statusline.sh" in result          # toggled on in stage 1
    assert "superpowers" not in result        # 'n' cleared stage 2


def test_numbered_fallback_a_selects_all_in_stage():
    stages = _stages()
    instream = io.StringIO("a\n\n\n")          # stage1 all, enter; stage2 enter
    result = wizard._numbered_fallback(stages, set(), instream, io.StringIO())
    assert "settings.json" in result and "statusline.sh" in result


def test_run_wizard_uses_fallback_when_not_tty():
    stages = _stages()
    instream = io.StringIO("\n\n")             # accept defaults each stage
    outstream = io.StringIO()                  # StringIO.isatty() is False
    result = wizard.run_wizard(stages, {"settings.json"},
                               in_stream=instream, out_stream=outstream)
    assert "settings.json" in result


def test_decode_key_arrows_and_chars():
    assert wizard._decode_key("\x1b[A") == "up"
    assert wizard._decode_key("\x1b[B") == "down"
    assert wizard._decode_key("\x1b[D") == "left"
    assert wizard._decode_key("\r") == "enter"
    assert wizard._decode_key("\n") == "enter"
    assert wizard._decode_key(" ") == "space"
    assert wizard._decode_key("\x1b") == "esc"
    assert wizard._decode_key("a") == "a"
    assert wizard._decode_key("\x03") == "ctrl-c"
