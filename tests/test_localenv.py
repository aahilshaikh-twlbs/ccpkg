import os

import pytest

from ccpkg import localenv


def test_defaults_shape():
    # Contract §3: exact default keys and values.
    assert localenv.DEFAULTS == {
        "CODE_ROOT": "$HOME/Documents/Code",
        "VAULT_ROOT": "",
        "AWS_PROFILE": "",
        "OVERLAY_REPO": "",
        "OVERLAY_DIR": "",
    }
    # DEFAULTS must not be mutated by load(); prove load returns a distinct object.
    before = dict(localenv.DEFAULTS)
    localenv.load(os.path.join(os.sep, "no", "such", "file.env"))
    assert localenv.DEFAULTS == before


def test_parse_basic_key_value():
    text = "CODE_ROOT=$HOME/Documents/Code\nAWS_PROFILE=work\n"
    assert localenv.parse_env_text(text) == {
        "CODE_ROOT": "$HOME/Documents/Code",
        "AWS_PROFILE": "work",
    }


def test_parse_ignores_blanks_and_comments():
    text = (
        "# a leading comment\n"
        "\n"
        "   \n"
        "CODE_ROOT=/repos\n"
        "   # indented comment\n"
        "VAULT_ROOT=/vault\n"
    )
    assert localenv.parse_env_text(text) == {
        "CODE_ROOT": "/repos",
        "VAULT_ROOT": "/vault",
    }


def test_parse_strips_quotes_and_whitespace():
    text = 'A="quoted value"\nB=\'single quoted\'\nC=  spaced  \nD="trailing"  \n'
    assert localenv.parse_env_text(text) == {
        "A": "quoted value",
        "B": "single quoted",
        "C": "spaced",
        "D": "trailing",
    }


def test_parse_keeps_equals_inside_value():
    # Only the first '=' splits key from value.
    text = "URL=https://example.com/path?a=1&b=2\n"
    assert localenv.parse_env_text(text) == {
        "URL": "https://example.com/path?a=1&b=2",
    }


def test_parse_skips_lines_without_equals():
    text = "CODE_ROOT=/repos\nnonsense line with no equals\nVAULT_ROOT=/v\n"
    assert localenv.parse_env_text(text) == {
        "CODE_ROOT": "/repos",
        "VAULT_ROOT": "/v",
    }


def test_expand_dollar_home(monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    assert localenv.expand("$HOME/Documents/Code", {}) == "/home/tester/Documents/Code"


def test_expand_braced_home(monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    assert localenv.expand("${HOME}/x", {}) == "/home/tester/x"


def test_expand_uses_env_dict_over_environ(monkeypatch):
    # Values from the passed env dict take precedence over os.environ.
    monkeypatch.setenv("CODE_ROOT", "/from/environ")
    assert localenv.expand("$CODE_ROOT/sub", {"CODE_ROOT": "/from/dict"}) == "/from/dict/sub"


def test_expand_falls_back_to_environ(monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "envprofile")
    assert localenv.expand("$AWS_PROFILE", {}) == "envprofile"


def test_expand_unknown_var_left_as_is(monkeypatch):
    monkeypatch.delenv("DEFINITELY_UNSET_VAR_XYZ", raising=False)
    assert localenv.expand("$DEFINITELY_UNSET_VAR_XYZ/end", {}) == "$DEFINITELY_UNSET_VAR_XYZ/end"


def test_expand_no_command_substitution(monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    # Command substitution syntax ($(...) and backticks) must be left verbatim — no shell
    # evaluation. Only $HOME expands. The input ends with a literal "/" immediately before
    # "$HOME", so the result is "...whoami`" + "/" + "/home/tester" (a deliberate double
    # slash); that is the correct text-substitution behavior.
    val = "$(echo pwned)/`whoami`/$HOME"
    assert localenv.expand(val, {}) == "$(echo pwned)/`whoami`//home/tester"
    assert localenv.expand("$(echo pwned)", {}) == "$(echo pwned)"
    assert localenv.expand("`whoami`", {}) == "`whoami`"


def test_load_missing_file_returns_expanded_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", "/home/tester")
    missing = str(tmp_path / "nope.env")
    result = localenv.load(missing)
    assert result["CODE_ROOT"] == "/home/tester/Documents/Code"
    assert result["VAULT_ROOT"] == ""
    assert result["AWS_PROFILE"] == ""
    assert result["OVERLAY_REPO"] == ""
    assert result["OVERLAY_DIR"] == ""


def test_load_file_overlays_defaults_and_expands(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", "/home/tester")
    p = tmp_path / "local.env"
    p.write_text(
        'CODE_ROOT="$HOME/code"\n'
        "VAULT_ROOT=$HOME/vault\n"
        "AWS_PROFILE=work\n"
    )
    result = localenv.load(str(p))
    assert result["CODE_ROOT"] == "/home/tester/code"
    assert result["VAULT_ROOT"] == "/home/tester/vault"
    assert result["AWS_PROFILE"] == "work"
    # Keys absent from the file fall back to (expanded) DEFAULTS.
    assert result["OVERLAY_REPO"] == ""
    assert result["OVERLAY_DIR"] == ""


def test_template_vars(monkeypatch):
    monkeypatch.setenv("HOME", "/home/tester")
    env = {
        "CODE_ROOT": "/home/tester/code",
        "VAULT_ROOT": "/home/tester/vault",
        "AWS_PROFILE": "work",
        "OVERLAY_REPO": "git@example.com:o/r.git",
        "OVERLAY_DIR": "/tmp/overlay",
    }
    tv = localenv.template_vars(env)
    assert tv == {
        "HOME": "/home/tester",
        "CODE_ROOT": "/home/tester/code",
        "VAULT_ROOT": "/home/tester/vault",
        "AWS_PROFILE": "work",
    }
    # OVERLAY_* are NOT template substitution vars.
    assert "OVERLAY_REPO" not in tv
    assert "OVERLAY_DIR" not in tv
