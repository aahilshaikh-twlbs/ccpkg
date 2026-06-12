from ccpkg import selectables


def test_selectables_cover_plugins_and_mboard():
    by_id = {s.id: s for s in selectables.SELECTABLES}
    assert {"superpowers", "frontend-design", "understand-anything"} <= set(by_id)
    assert "mboard" in by_id


def test_plugin_selectables_have_plugin_kind():
    for s in selectables.SELECTABLES:
        assert s.kind in {"plugin", "mboard", "pack"}, (
            "unexpected kind %r for %r" % (s.kind, s.id)
        )
        assert s.group
        assert s.desc
        assert isinstance(s.default, bool)


def test_plugin_ids_match_plugins_module():
    # selectable plugin ids are the short names of ccpkg.plugins.PLUGINS
    from ccpkg import plugins
    short = {p.split("@", 1)[0] for p in plugins.PLUGINS}
    sel_plugin_ids = {s.id for s in selectables.SELECTABLES if s.kind == "plugin"}
    assert sel_plugin_ids == short


def test_six_pack_selectables_present():
    by_id = {s.id: s for s in selectables.SELECTABLES if s.kind == "pack"}
    expected_ids = {
        "anthropic-skills", "mattpocock-skills", "composio-skills",
        "wshobson-agents", "voltagent-subagents", "awesome-cc-toolkit",
    }
    assert expected_ids == set(by_id)


def test_pack_selectables_have_correct_groups():
    by_id = {s.id: s for s in selectables.SELECTABLES if s.kind == "pack"}
    assert by_id["anthropic-skills"].group == "Skills"
    assert by_id["mattpocock-skills"].group == "Skills"
    assert by_id["composio-skills"].group == "Skills"
    assert by_id["wshobson-agents"].group == "Agents"
    assert by_id["voltagent-subagents"].group == "Agents"
    assert by_id["awesome-cc-toolkit"].group == "Agents"


def test_pack_selectables_are_default_false():
    for s in selectables.SELECTABLES:
        if s.kind == "pack":
            assert s.default is False, "pack %r must default to False" % s.id
