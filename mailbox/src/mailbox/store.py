import json
import os
import tempfile
from typing import Iterator
from typing import Optional
from typing import Tuple


def atomic_write_json(path, obj):
    # type: (str, dict) -> None
    dir_path = os.path.dirname(path) or "."
    os.makedirs(dir_path, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=dir_path)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_json(path):
    # type: (str) -> Optional[dict]
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def iter_json(dir_path):
    # type: (str) -> Iterator[Tuple[str, dict]]
    try:
        names = os.listdir(dir_path)
    except OSError:
        return
    for name in sorted(names):
        if not name.endswith(".json"):
            continue
        # Skip crash-orphaned temp files left behind by atomic_write_json
        # (prefix ".tmp-", suffix ".json"); they are valid JSON but not records.
        if name.startswith(".tmp-"):
            continue
        file_path = os.path.join(dir_path, name)
        parsed = read_json(file_path)
        if parsed is None:
            continue
        yield (file_path, parsed)


def remove(path):
    # type: (str) -> None
    try:
        os.unlink(path)
    except OSError:
        pass
