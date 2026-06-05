from ccpkg import manifest, selectables, selection, profile


def _items():
    return [
        manifest.Item(path="settings.json", mode="merge", group="Core",
                      desc="settings", default=True),
        manifest.Item(path="skills/shannon", mode="symlink", group="Skills",
                      desc="pentester", default=True),
        manifest.Item(path="agents/x.md", mode="symlink", layer="overlay",
                      group="Overlay", desc="overlay agent", default=True),
    ]


def test_build_stages_orders_groups_and_skips_empty():
    stages = selection.build_stages(_items(), selectables.SELECTABLES,
                                    overlay_present=False)
    names = [s.name for s in stages]
    # Core before Skills before Plugins before Coordination; Overlay skipped.
    assert names == ["Core", "Skills", "Plugins", "Coordination"]


def test_build_stages_includes_overlay_when_present():
    stages = selection.build_stages(_items(), selectables.SELECTABLES,
                                    overlay_present=True)
    assert "Overlay" in [s.name for s in stages]


def test_default_ids_are_default_true_entries():
    ids = selection.default_ids(_items(), selectables.SELECTABLES,
                                overlay_present=False)
    assert "settings.json" in ids
    assert "skills/shannon" in ids
    assert "superpowers" in ids          # selectable default
    assert "agents/x.md" not in ids      # overlay absent


def test_resolve_uses_profile_when_present_and_not_reconfigure():
    prof = profile.Profile(selected=["settings.json"], deselected=["skills/shannon"])
    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=prof, is_tty=True, reconfigure=False, run_wizard=None)
    assert ids == {"settings.json"}


def test_resolve_falls_back_to_defaults_when_no_profile_no_tty():
    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=None, is_tty=False, reconfigure=False, run_wizard=None)
    assert "settings.json" in ids and "superpowers" in ids


def test_resolve_runs_wizard_when_tty_and_no_profile():
    calls = {}

    def fake_wizard(stages, preselected):
        calls["preselected"] = preselected
        return {"settings.json"}

    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=None, is_tty=True, reconfigure=False, run_wizard=fake_wizard)
    assert ids == {"settings.json"}
    # wizard was pre-ticked from defaults
    assert "superpowers" in calls["preselected"]


def test_resolve_reconfigure_runs_wizard_even_with_profile():
    prof = profile.Profile(selected=["settings.json"], deselected=[])

    def fake_wizard(stages, preselected):
        # pre-ticked from the existing profile's selected set
        assert preselected == {"settings.json"}
        return {"settings.json", "skills/shannon"}

    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=prof, is_tty=True, reconfigure=True, run_wizard=fake_wizard)
    assert ids == {"settings.json", "skills/shannon"}
