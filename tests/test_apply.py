import json
import os

from ccpkg import apply, config, manifest


def _read(p):
    with open(p) as fh:
        return fh.read()


# ---------- backup_then_write ----------

def test_backup_then_write_new_file_no_backup(tmp_path):
    target = str(tmp_path / "sub" / "dir" / "f.txt")
    backup = apply.backup_then_write(target, "hello")
    assert backup is None
    assert os.path.isfile(target)
    assert _read(target) == "hello"


def test_backup_then_write_overwrite_differing_makes_backup(tmp_path):
    target = str(tmp_path / "f.txt")
    with open(target, "w") as fh:
        fh.write("old")
    backup = apply.backup_then_write(target, "new")
    assert backup == target + config.backup_suffix()
    assert _read(backup) == "old"
    assert _read(target) == "new"


def test_backup_then_write_same_content_no_backup(tmp_path):
    target = str(tmp_path / "f.txt")
    with open(target, "w") as fh:
        fh.write("same")
    backup = apply.backup_then_write(target, "same")
    assert backup is None
    assert not os.path.exists(target + config.backup_suffix())
    assert _read(target) == "same"


# ---------- apply_symlink ----------

def test_apply_symlink_creates_link(tmp_path):
    src = str(tmp_path / "src.sh")
    with open(src, "w") as fh:
        fh.write("body")
    target = str(tmp_path / "out" / "link.sh")
    result = apply.apply_symlink(src, target)
    assert result == "linked"
    assert os.path.islink(target)
    assert os.path.realpath(target) == os.path.realpath(src)


def test_apply_symlink_idempotent(tmp_path):
    src = str(tmp_path / "src.sh")
    with open(src, "w") as fh:
        fh.write("body")
    target = str(tmp_path / "link.sh")
    apply.apply_symlink(src, target)
    result = apply.apply_symlink(src, target)
    assert result == "ok"
    assert os.path.islink(target)
    assert os.path.realpath(target) == os.path.realpath(src)


def test_apply_symlink_replaces_wrong_link(tmp_path):
    src = str(tmp_path / "src.sh")
    other = str(tmp_path / "other.sh")
    for p in (src, other):
        with open(p, "w") as fh:
            fh.write("body")
    target = str(tmp_path / "link.sh")
    os.symlink(other, target)
    result = apply.apply_symlink(src, target)
    assert result == "linked"
    assert os.path.realpath(target) == os.path.realpath(src)


def test_apply_symlink_backs_up_real_file(tmp_path):
    src = str(tmp_path / "src.sh")
    with open(src, "w") as fh:
        fh.write("newbody")
    target = str(tmp_path / "real.sh")
    with open(target, "w") as fh:
        fh.write("livebody")
    result = apply.apply_symlink(src, target)
    assert result == "linked"
    assert os.path.islink(target)
    backup = target + config.backup_suffix()
    assert _read(backup) == "livebody"


# ---------- apply_template ----------

def test_apply_template_substitutes_and_strips_tmpl(tmp_path):
    src = str(tmp_path / "settings.local.json.tmpl")
    with open(src, "w") as fh:
        fh.write('{"codeRoot": "${CODE_ROOT}"}\n')
    target = str(tmp_path / "out" / "settings.local.json.tmpl")
    result = apply.apply_template(
        src, target, {"CODE_ROOT": "/code"}, False
    )
    written = str(tmp_path / "out" / "settings.local.json")
    assert result in ("ok", "rendered")
    assert os.path.isfile(written)
    assert not os.path.exists(target)
    assert json.loads(_read(written)) == {"codeRoot": "/code"}


# ---------- apply_merge_json ----------

def test_apply_merge_json_base_wins_live_preserved(tmp_path):
    src = str(tmp_path / "settings.json")
    with open(src, "w") as fh:
        fh.write(json.dumps({"a": 1, "shared": "base"}))
    target = str(tmp_path / "out" / "settings.json")
    os.makedirs(os.path.dirname(target))
    with open(target, "w") as fh:
        fh.write(json.dumps({"liveOnly": True, "shared": "live"}))
    result = apply.apply_merge_json(src, target)
    assert result in ("ok", "merged")
    merged = json.loads(_read(target))
    assert merged["a"] == 1
    assert merged["shared"] == "base"
    assert merged["liveOnly"] is True
    backup = target + config.backup_suffix()
    assert os.path.isfile(backup)
    assert json.loads(_read(backup)) == {"liveOnly": True, "shared": "live"}


# ---------- apply_item ----------

def test_apply_item_symlink(tmp_repo, tmp_home):
    src_base = os.path.join(tmp_repo, "home", ".claude")
    item = manifest.Item(path="statusline.sh", mode="symlink", os="any", layer="base")
    result = apply.apply_item(item, src_base, tmp_home, {}, False)
    assert result == "linked"
    assert os.path.islink(os.path.join(tmp_home, "statusline.sh"))


def test_apply_item_template_strips_tmpl_in_target(tmp_repo, tmp_home):
    src_base = os.path.join(tmp_repo, "home", ".claude")
    item = manifest.Item(
        path="settings.local.json.tmpl", mode="template", os="any", layer="base"
    )
    apply.apply_item(item, src_base, tmp_home, {"AWS_PROFILE": "acme"}, False)
    written = os.path.join(tmp_home, "settings.local.json")
    assert os.path.isfile(written)
    assert json.loads(_read(written)) == {"awsProfile": "acme"}


def test_apply_item_merge(tmp_repo, tmp_home):
    src_base = os.path.join(tmp_repo, "home", ".claude")
    live = os.path.join(tmp_home, "settings.json")
    with open(live, "w") as fh:
        fh.write(json.dumps({"keep": 1}))
    item = manifest.Item(path="settings.json", mode="merge", os="any", layer="base")
    apply.apply_item(item, src_base, tmp_home, {}, False)
    merged = json.loads(_read(live))
    assert merged["keep"] == 1
    assert merged["model"] == "claude-base"


# ---------- apply_layer ----------

def test_apply_layer_filters_and_returns_pairs(tmp_repo, tmp_home):
    src_base = os.path.join(tmp_repo, "home", ".claude")
    items = [
        manifest.Item(path="statusline.sh", mode="symlink", os="any", layer="base"),
        manifest.Item(path="overlay-only", mode="symlink", os="any", layer="overlay"),
        manifest.Item(path="linux-only.sh", mode="symlink", os="linux", layer="base"),
    ]
    results = apply.apply_layer(
        items, "base", src_base, tmp_home, {}, False, "darwin"
    )
    paths = [p for (p, r) in results]
    assert "statusline.sh" in paths
    assert "overlay-only" not in paths      # wrong layer filtered
    assert "linux-only.sh" not in paths      # wrong os filtered
    assert all(isinstance(r, str) for (p, r) in results)
    assert dict(results)["statusline.sh"] == "linked"
