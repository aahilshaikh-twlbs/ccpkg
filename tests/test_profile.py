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
