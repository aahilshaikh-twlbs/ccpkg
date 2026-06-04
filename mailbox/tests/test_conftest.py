import os

from mailbox import config


def test_tmp_home_sets_env(tmp_home):
    assert os.environ["MAILBOX_HOME"] == str(tmp_home)
    assert os.environ["MAILBOX_SOCKET"] == str(tmp_home / "mailboxd.sock")
    assert tmp_home.is_dir()


def test_tmp_home_drives_config(tmp_home):
    assert config.home() == str(tmp_home)
    assert config.state_dir() == os.path.join(str(tmp_home), "state")
    assert config.socket_path() == str(tmp_home / "mailboxd.sock")
    assert config.pidfile() == os.path.join(str(tmp_home), "mailboxd.pid")
    assert config.logfile() == os.path.join(str(tmp_home), "mailboxd.log")


def test_clock_fixture_advances(clock):
    assert clock() == 1000.0
    clock.advance(45)
    assert clock() == 1045.0
