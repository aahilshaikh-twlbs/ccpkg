from ccpkg import selectables


def test_selectables_cover_plugins_and_mboard():
    by_id = {s.id: s for s in selectables.SELECTABLES}
    assert {"superpowers", "frontend-design", "understand-anything"} <= set(by_id)
    assert "mboard" in by_id


def test_plugin_selectables_have_plugin_kind():
    for s in selectables.SELECTABLES:
        if s.id == "mboard":
            assert s.kind == "mboard"
        else:
            assert s.kind == "plugin"
        assert s.group
        assert s.desc
        assert isinstance(s.default, bool)


def test_plugin_ids_match_plugins_module():
    # selectable plugin ids are the short names of ccpkg.plugins.PLUGINS
    from ccpkg import plugins
    short = {p.split("@", 1)[0] for p in plugins.PLUGINS}
    sel_plugin_ids = {s.id for s in selectables.SELECTABLES if s.kind == "plugin"}
    assert sel_plugin_ids == short
