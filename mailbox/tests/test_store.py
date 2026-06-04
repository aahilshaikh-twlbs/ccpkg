import json
import os

from mailbox import store


def test_round_trip_write_then_read(tmp_path):
    path = os.path.join(str(tmp_path), "obj.json")
    obj = {"id": "clm_abc", "paths": ["/a/b", "/a/c"], "n": 3, "released": False}

    store.atomic_write_json(path, obj)

    assert os.path.exists(path)
    assert store.read_json(path) == obj


def test_read_json_malformed_returns_none(tmp_path):
    path = os.path.join(str(tmp_path), "bad.json")
    with open(path, "w") as f:
        f.write("{not valid json")

    assert store.read_json(path) is None


def test_read_json_missing_returns_none(tmp_path):
    path = os.path.join(str(tmp_path), "does-not-exist.json")

    assert store.read_json(path) is None


def test_iter_json_yields_good_skips_malformed(tmp_path):
    dir_path = os.path.join(str(tmp_path), "claims")
    store.atomic_write_json(os.path.join(dir_path, "a.json"), {"id": "a"})
    store.atomic_write_json(os.path.join(dir_path, "b.json"), {"id": "b"})
    with open(os.path.join(dir_path, "c.json"), "w") as f:
        f.write("{broken")
    # non-json file must be ignored entirely
    with open(os.path.join(dir_path, "ignore.txt"), "w") as f:
        f.write("nope")

    results = dict(store.iter_json(dir_path))

    assert results == {
        os.path.join(dir_path, "a.json"): {"id": "a"},
        os.path.join(dir_path, "b.json"): {"id": "b"},
    }


def test_iter_json_skips_orphaned_tmp_files(tmp_path):
    # A crash-orphaned temp file from atomic_write_json (prefix ".tmp-",
    # suffix ".json") is valid JSON but must NOT be loaded as a real record.
    dir_path = os.path.join(str(tmp_path), "claims")
    store.atomic_write_json(os.path.join(dir_path, "real.json"), {"id": "real"})
    # Manually drop an orphaned temp file with valid JSON in the same dir.
    with open(os.path.join(dir_path, ".tmp-orphan.json"), "w") as f:
        json.dump({"id": "orphan"}, f)

    results = dict(store.iter_json(dir_path))

    assert results == {os.path.join(dir_path, "real.json"): {"id": "real"}}


def test_iter_json_missing_dir_yields_nothing(tmp_path):
    dir_path = os.path.join(str(tmp_path), "no-such-dir")

    assert list(store.iter_json(dir_path)) == []


def test_remove_deletes_existing(tmp_path):
    path = os.path.join(str(tmp_path), "obj.json")
    store.atomic_write_json(path, {"id": "x"})
    assert os.path.exists(path)

    store.remove(path)

    assert not os.path.exists(path)


def test_remove_missing_does_not_raise(tmp_path):
    path = os.path.join(str(tmp_path), "does-not-exist.json")

    # must not raise
    store.remove(path)

    assert not os.path.exists(path)
