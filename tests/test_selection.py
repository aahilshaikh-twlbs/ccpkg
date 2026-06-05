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
    # Profile replay MERGES current defaults: selected items, plus any default-on
    # feature not explicitly deselected. An explicitly deselected item stays out.
    prof = profile.Profile(selected=["settings.json"], deselected=["skills/shannon"])
    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=prof, is_tty=True, reconfigure=False, run_wizard=None)
    assert "settings.json" in ids               # explicitly selected
    assert "skills/shannon" not in ids          # explicitly deselected stays out
    assert "superpowers" in ids                 # new default-on surfaces


def test_resolve_profile_replay_includes_new_default_on_feature():
    # A feature default-on now but absent from the saved profile (not in selected,
    # not in deselected) must surface on headless replay — not be silently dropped.
    prof = profile.Profile(selected=["settings.json"], deselected=[])
    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=prof, is_tty=False, reconfigure=False, run_wizard=None)
    assert "superpowers" in ids       # new default-on, never in the old profile
    assert "skills/shannon" in ids    # also default-on


def test_resolve_profile_replay_respects_deselected():
    # An explicitly deselected default-on feature stays OUT on replay.
    prof = profile.Profile(selected=["settings.json"], deselected=["superpowers"])
    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=prof, is_tty=False, reconfigure=False, run_wizard=None)
    assert "settings.json" in ids
    assert "superpowers" not in ids


def test_resolve_reconfigure_without_tty_does_not_run_wizard():
    # --yes forces is_tty False in the CLI; --reconfigure must not override it.
    prof = profile.Profile(selected=["settings.json"], deselected=["skills/shannon"])
    called = {"wizard": False}

    def fake_wizard(stages, preselected):
        called["wizard"] = True
        return {"x"}

    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=prof, is_tty=False, reconfigure=True, run_wizard=fake_wizard)
    assert called["wizard"] is False
    assert "settings.json" in ids
    assert "skills/shannon" not in ids


def test_resolve_reconfigure_no_wizard_falls_through_to_profile():
    # reconfigure + run_wizard=None cleanly falls through to the profile replay.
    prof = profile.Profile(selected=["settings.json"], deselected=[])
    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=prof, is_tty=True, reconfigure=True, run_wizard=None)
    assert "settings.json" in ids
    assert "superpowers" in ids


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


def test_resolve_interactive_with_profile_reopens_picker_prefilled():
    # The update flow: a TTY run WITH a saved profile and NO --reconfigure now
    # reopens the picker (pre-ticked from the profile merged with defaults),
    # instead of silently replaying. This is how a re-run becomes an update.
    prof = profile.Profile(selected=["settings.json"], deselected=["skills/shannon"])
    calls = {}

    def fake_wizard(stages, preselected):
        calls["preselected"] = set(preselected)
        return {"settings.json", "skills/shannon"}

    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=prof, is_tty=True, reconfigure=False, run_wizard=fake_wizard)
    assert "preselected" in calls                       # wizard DID run
    assert "settings.json" in calls["preselected"]      # from profile.selected
    assert "skills/shannon" not in calls["preselected"] # explicitly deselected
    assert "superpowers" in calls["preselected"]        # new default-on merged in
    assert ids == {"settings.json", "skills/shannon"}


def test_resolve_reconfigure_runs_wizard_even_with_profile():
    prof = profile.Profile(selected=["settings.json"], deselected=[])

    def fake_wizard(stages, preselected):
        # pre-ticked from profile.selected MERGED with current defaults, so a new
        # default-on feature shows ticked.
        assert "settings.json" in preselected
        assert "superpowers" in preselected
        return {"settings.json", "skills/shannon"}

    ids = selection.resolve_selection(
        _items(), selectables.SELECTABLES, overlay_present=False,
        profile_obj=prof, is_tty=True, reconfigure=True, run_wizard=fake_wizard)
    assert ids == {"settings.json", "skills/shannon"}
