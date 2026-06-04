import copy

from ccpkg import plugins


def test_ensure_adds_enabled_plugins_and_marketplaces():
    out = plugins.ensure_plugin_settings({})
    # every declared plugin is enabled
    assert out["enabledPlugins"] == {p: True for p in plugins.PLUGINS}
    # each declared marketplace is present with its declared value
    for name, spec in plugins.MARKETPLACES.items():
        assert out["extraKnownMarketplaces"][name] == spec


def test_ensure_returns_new_dict_does_not_mutate_input():
    original = {"some": "value"}
    snapshot = copy.deepcopy(original)
    out = plugins.ensure_plugin_settings(original)
    # input untouched
    assert original == snapshot
    assert "enabledPlugins" not in original
    # output is a distinct object that preserves unrelated keys
    assert out is not original
    assert out["some"] == "value"


def test_ensure_preserves_existing_unrelated_plugin_and_marketplace_entries():
    settings = {
        "enabledPlugins": {"already@somewhere": True},
        "extraKnownMarketplaces": {"keepme": {"source": "x"}},
    }
    out = plugins.ensure_plugin_settings(settings)
    # pre-existing entries survive
    assert out["enabledPlugins"]["already@somewhere"] is True
    assert out["extraKnownMarketplaces"]["keepme"] == {"source": "x"}
    # declared entries added
    for p in plugins.PLUGINS:
        assert out["enabledPlugins"][p] is True
    for name, spec in plugins.MARKETPLACES.items():
        assert out["extraKnownMarketplaces"][name] == spec


def test_ensure_is_idempotent():
    once = plugins.ensure_plugin_settings({})
    twice = plugins.ensure_plugin_settings(once)
    assert twice == once


def test_ensure_does_not_override_disabled_plugin_to_true_for_declared():
    # declared plugins are forced True even if previously False
    settings = {"enabledPlugins": {plugins.PLUGINS[0]: False}}
    out = plugins.ensure_plugin_settings(settings)
    assert out["enabledPlugins"][plugins.PLUGINS[0]] is True


def test_cli_install_no_claude_does_nothing(fake_run):
    result = plugins.cli_install(run=fake_run, have=lambda cmd: False)
    # claude absent -> every plugin reported "skipped", nothing executed
    assert result == {p: "skipped" for p in plugins.PLUGINS}
    assert fake_run.calls == []


def test_cli_install_with_fake_run_adds_marketplace_and_installs(fake_run):
    result = plugins.cli_install(run=fake_run, have=lambda cmd: True)
    # marketplace add issued exactly once, first
    assert fake_run.calls[0] == [
        "claude", "plugin", "marketplace", "add",
        "Lum1104/Understand-Anything",
    ]
    # one install per declared plugin, preserving order
    install_calls = fake_run.calls[1:]
    assert install_calls == [
        ["claude", "plugin", "install", p] for p in plugins.PLUGINS
    ]
    # every plugin reported installed
    assert result == {p: "installed" for p in plugins.PLUGINS}


def test_cli_install_never_raises_on_run_failure():
    def boom(cmd, *args, **kwargs):
        raise OSError("exec failed")

    # have=True so it attempts to run; boom raises -> must be swallowed
    result = plugins.cli_install(run=boom, have=lambda cmd: True)
    assert result == {p: "failed" for p in plugins.PLUGINS}
