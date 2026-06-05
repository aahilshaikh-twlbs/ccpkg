import os

from ccpkg import profile


def test_save_then_load_roundtrip(tmp_path):
    home = str(tmp_path)
    p = profile.Profile(selected=["settings.json", "superpowers"],
                        deselected=["skills/shannon"])
    profile.save(home, p)
    assert os.path.exists(os.path.join(home, ".ccpkg-profile.json"))
    loaded = profile.load(home)
    assert loaded is not None
    assert loaded.selected == ["settings.json", "superpowers"]
    assert loaded.deselected == ["skills/shannon"]


def test_load_missing_returns_none(tmp_path):
    assert profile.load(str(tmp_path)) is None


def test_load_corrupt_returns_none(tmp_path):
    home = str(tmp_path)
    with open(os.path.join(home, ".ccpkg-profile.json"), "w") as fh:
        fh.write("{ not json")
    assert profile.load(home) is None


def test_load_empty_dict_returns_none(tmp_path):
    # Fix H: a {} (or any dict missing BOTH keys) is treated as absent so the
    # caller falls back to defaults/wizard instead of installing nothing.
    home = str(tmp_path)
    with open(os.path.join(home, ".ccpkg-profile.json"), "w") as fh:
        fh.write("{}")
    assert profile.load(home) is None


def test_load_dict_without_either_key_returns_none(tmp_path):
    home = str(tmp_path)
    with open(os.path.join(home, ".ccpkg-profile.json"), "w") as fh:
        fh.write('{"other": 1}')
    assert profile.load(home) is None


def test_load_with_only_selected_key_is_honored(tmp_path):
    # An explicit key (even an empty list) means the profile is intentional.
    home = str(tmp_path)
    with open(os.path.join(home, ".ccpkg-profile.json"), "w") as fh:
        fh.write('{"selected": []}')
    loaded = profile.load(home)
    assert loaded is not None
    assert loaded.selected == []
    assert loaded.deselected == []


def test_load_with_only_deselected_key_is_honored(tmp_path):
    home = str(tmp_path)
    with open(os.path.join(home, ".ccpkg-profile.json"), "w") as fh:
        fh.write('{"deselected": ["skills/shannon"]}')
    loaded = profile.load(home)
    assert loaded is not None
    assert loaded.selected == []
    assert loaded.deselected == ["skills/shannon"]
