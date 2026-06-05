import os

from ccpkg import config, manifest, profile, uninstall


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def test_remove_symlink_restores_backup(tmp_path):
    home = str(tmp_path)
    real = os.path.join(home, "src.sh")
    _write(real, "live-link-content")
    target = os.path.join(home, "statusline.sh")
    os.symlink(real, target)
    _write(target + config.backup_suffix(), "ORIGINAL")

    item = manifest.Item(path="statusline.sh", mode="symlink")
    status = uninstall._remove_one(item, target)

    assert "removed-symlink" in status and "restored-backup" in status
    assert not os.path.islink(target)
    assert open(target).read() == "ORIGINAL"
    assert not os.path.exists(target + config.backup_suffix())


def test_remove_symlink_no_backup_just_removes(tmp_path):
    home = str(tmp_path)
    real = os.path.join(home, "src.sh")
    _write(real, "x")
    target = os.path.join(home, "statusline.sh")
    os.symlink(real, target)

    item = manifest.Item(path="statusline.sh", mode="symlink")
    assert uninstall._remove_one(item, target) == "removed-symlink"
    assert not os.path.lexists(target)


def test_merge_target_restores_backup_when_present(tmp_path):
    home = str(tmp_path)
    target = os.path.join(home, "settings.json")
    _write(target, '{"model":"opus","mailboxhook":1}')
    _write(target + config.backup_suffix(), '{"model":"sonnet"}')

    item = manifest.Item(path="settings.json", mode="merge")
    assert uninstall._remove_one(item, target) == "restored-backup"
    assert open(target).read() == '{"model":"sonnet"}'


def test_merge_target_left_when_no_backup(tmp_path):
    # settings.json must NEVER be deleted outright (may hold the user's own keys).
    home = str(tmp_path)
    target = os.path.join(home, "settings.json")
    _write(target, '{"model":"opus"}')

    item = manifest.Item(path="settings.json", mode="merge")
    status = uninstall._remove_one(item, target)
    assert "left" in status
    assert os.path.isfile(target)                 # still there


def test_template_target_uses_stripped_name(tmp_path):
    # A .tmpl item renders to the name WITHOUT .tmpl; uninstall must target that.
    home = str(tmp_path)
    item = manifest.Item(path="settings.local.json.tmpl", mode="template")
    target = uninstall._target_for(item, home)
    assert target == os.path.join(home, "settings.local.json")


def test_uninstall_removes_profile_and_mailbox(tmp_path, monkeypatch):
    home = str(tmp_path)
    # Fake an installed tree: a symlinked statusline, a profile, a mailbox dir.
    real = os.path.join(home, "src.sh")
    _write(real, "x")
    os.symlink(real, os.path.join(home, "statusline.sh"))
    profile.save(home, profile.Profile(selected=["statusline.sh"], deselected=[]))
    os.makedirs(os.path.join(home, "mailbox"))
    _write(os.path.join(home, "mailbox", "mailboxd.log"), "log")

    monkeypatch.setattr(
        manifest, "parse",
        lambda _p: [manifest.Item(path="statusline.sh", mode="symlink")])
    monkeypatch.setattr(config, "manifest_path", lambda _root: "ignored")

    results = uninstall.uninstall("root", home, "darwin")
    d = dict(results)

    assert d["statusline.sh"] == "removed-symlink"
    assert d["mailbox"] == "removed"
    assert d[profile.PROFILE_NAME] == "removed"
    assert not os.path.lexists(os.path.join(home, "statusline.sh"))
    assert not os.path.isdir(os.path.join(home, "mailbox"))
    assert profile.load(home) is None


def test_plan_lists_targets(tmp_path, monkeypatch):
    home = str(tmp_path)
    monkeypatch.setattr(
        manifest, "parse",
        lambda _p: [manifest.Item(path="statusline.sh", mode="symlink"),
                    manifest.Item(path="settings.local.json.tmpl", mode="template")])
    monkeypatch.setattr(config, "manifest_path", lambda _root: "ignored")

    targets = uninstall.plan("root", home, "darwin")
    assert os.path.join(home, "statusline.sh") in targets
    assert os.path.join(home, "settings.local.json") in targets   # .tmpl stripped
