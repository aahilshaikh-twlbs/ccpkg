import json

from ccpkg import mergejson


def test_deep_merge_nested_recurses_key_by_key():
    into = {"a": {"x": 1, "y": 2}, "b": 10}
    src = {"a": {"y": 99, "z": 3}, "c": 20}
    result = mergejson.deep_merge(into, src)
    assert result == {"a": {"x": 1, "y": 99, "z": 3}, "b": 10, "c": 20}


def test_deep_merge_src_wins_on_scalar_conflict():
    into = {"k": "old", "keep": 1}
    src = {"k": "new"}
    result = mergejson.deep_merge(into, src)
    assert result["k"] == "new"
    assert result["keep"] == 1


def test_deep_merge_lists_are_replaced_not_concatenated():
    into = {"perms": ["a", "b", "c"]}
    src = {"perms": ["x"]}
    result = mergejson.deep_merge(into, src)
    assert result["perms"] == ["x"]


def test_deep_merge_src_replaces_dict_with_scalar():
    into = {"k": {"nested": 1}}
    src = {"k": 5}
    result = mergejson.deep_merge(into, src)
    assert result["k"] == 5


def test_deep_merge_src_replaces_scalar_with_dict():
    into = {"k": 5}
    src = {"k": {"nested": 1}}
    result = mergejson.deep_merge(into, src)
    assert result["k"] == {"nested": 1}


def test_deep_merge_does_not_mutate_inputs():
    into = {"a": {"x": 1}, "list": [1, 2]}
    src = {"a": {"y": 2}, "list": [9]}
    into_snapshot = {"a": {"x": 1}, "list": [1, 2]}
    src_snapshot = {"a": {"y": 2}, "list": [9]}
    mergejson.deep_merge(into, src)
    assert into == into_snapshot
    assert src == src_snapshot


def test_deep_merge_nested_result_is_independent_copy():
    into = {"a": {"x": 1}}
    src = {"b": {"y": 2}}
    result = mergejson.deep_merge(into, src)
    result["a"]["x"] = 999
    result["b"]["y"] = 888
    assert into == {"a": {"x": 1}}
    assert src == {"b": {"y": 2}}


def test_deep_merge_nested_list_value_is_not_shared_with_src():
    src = {"perms": ["x", "y"]}
    result = mergejson.deep_merge({}, src)
    result["perms"].append("z")
    assert src == {"perms": ["x", "y"]}


def test_merge_settings_file_base_keys_win_over_live(tmp_path):
    live = tmp_path / "settings.json"
    live.write_text(json.dumps({"model": "old", "live_only": True}))
    base_obj = {"model": "new", "enabledPlugins": {"p": True}}
    result = mergejson.merge_settings_file(str(live), base_obj)
    assert result["model"] == "new"
    assert result["live_only"] is True
    assert result["enabledPlugins"] == {"p": True}


def test_merge_settings_file_missing_file_is_empty_live(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    base_obj = {"model": "base", "x": 1}
    result = mergejson.merge_settings_file(str(missing), base_obj)
    assert result == {"model": "base", "x": 1}


def test_merge_settings_file_malformed_live_tolerated(tmp_path):
    live = tmp_path / "settings.json"
    live.write_text("{ this is not valid json ]")
    base_obj = {"model": "base"}
    result = mergejson.merge_settings_file(str(live), base_obj)
    assert result == {"model": "base"}


def test_merge_settings_file_does_not_mutate_base_obj(tmp_path):
    live = tmp_path / "settings.json"
    live.write_text(json.dumps({"live_only": 1}))
    base_obj = {"nested": {"k": 1}}
    base_snapshot = {"nested": {"k": 1}}
    result = mergejson.merge_settings_file(str(live), base_obj)
    result["nested"]["k"] = 999
    assert base_obj == base_snapshot
