import re

import pytest

from ccpkg import template


# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------

def make_vars(home="/home/me", code_root="/home/me/Documents/Code",
              vault_root="/home/me/Vault", aws_profile="acme-dev"):
    # mirrors the dict shape localenv.template_vars(env) returns:
    # HOME plus CODE_ROOT / VAULT_ROOT / AWS_PROFILE.
    return {
        "HOME": home,
        "CODE_ROOT": code_root,
        "VAULT_ROOT": vault_root,
        "AWS_PROFILE": aws_profile,
    }


# ---------------------------------------------------------------------------
# marker constants
# ---------------------------------------------------------------------------

def test_marker_constants_have_expected_values():
    assert template.VAULT_BEGIN == "# ccpkg:vault:start"
    assert template.VAULT_END == "# ccpkg:vault:end"


# ---------------------------------------------------------------------------
# substitute
# ---------------------------------------------------------------------------

def test_substitute_replaces_known_vars():
    text = "code lives at ${CODE_ROOT} and vault at ${VAULT_ROOT}"
    out = template.substitute(text, make_vars())
    assert out == "code lives at /home/me/Documents/Code and vault at /home/me/Vault"


def test_substitute_leaves_unknown_vars_as_is():
    text = "known=${CODE_ROOT} unknown=${NOPE}"
    out = template.substitute(text, make_vars())
    assert out == "known=/home/me/Documents/Code unknown=${NOPE}"


def test_substitute_replaces_multiple_occurrences():
    text = "${AWS_PROFILE}/${AWS_PROFILE}"
    out = template.substitute(text, make_vars(aws_profile="p1"))
    assert out == "p1/p1"


def test_substitute_does_not_touch_bare_dollar_or_no_braces():
    text = "price is $5 and var is $CODE_ROOT"
    out = template.substitute(text, make_vars())
    assert out == "price is $5 and var is $CODE_ROOT"


def test_substitute_empty_value_substitutes_to_empty():
    text = "x${VAULT_ROOT}y"
    out = template.substitute(text, make_vars(vault_root=""))
    assert out == "xy"


# ---------------------------------------------------------------------------
# strip_optional_blocks
# ---------------------------------------------------------------------------

def test_strip_optional_blocks_disabled_removes_block_inclusive():
    text = (
        "line a\n"
        "# ccpkg:vault:start\n"
        "vault ref ${VAULT_ROOT}\n"
        "# ccpkg:vault:end\n"
        "line b\n"
    )
    out = template.strip_optional_blocks(text, enabled=False)
    assert out == "line a\nline b\n"


def test_strip_optional_blocks_enabled_removes_only_marker_lines():
    text = (
        "line a\n"
        "# ccpkg:vault:start\n"
        "vault ref ${VAULT_ROOT}\n"
        "# ccpkg:vault:end\n"
        "line b\n"
    )
    out = template.strip_optional_blocks(text, enabled=True)
    assert out == "line a\nvault ref ${VAULT_ROOT}\nline b\n"


def test_strip_optional_blocks_tolerant_of_html_comment_wrappers_disabled():
    text = (
        "head\n"
        "<!-- ccpkg:vault:start -->\n"
        "secret block\n"
        "<!-- ccpkg:vault:end -->\n"
        "tail\n"
    )
    out = template.strip_optional_blocks(text, enabled=False)
    assert out == "head\ntail\n"


def test_strip_optional_blocks_tolerant_of_html_comment_wrappers_enabled():
    text = (
        "head\n"
        "<!-- ccpkg:vault:start -->\n"
        "secret block\n"
        "<!-- ccpkg:vault:end -->\n"
        "tail\n"
    )
    out = template.strip_optional_blocks(text, enabled=True)
    assert out == "head\nsecret block\ntail\n"


def test_strip_optional_blocks_handles_multiple_blocks_disabled():
    text = (
        "a\n"
        "# ccpkg:vault:start\n"
        "b\n"
        "# ccpkg:vault:end\n"
        "c\n"
        "<!-- ccpkg:vault:start -->\n"
        "d\n"
        "<!-- ccpkg:vault:end -->\n"
        "e\n"
    )
    out = template.strip_optional_blocks(text, enabled=False)
    assert out == "a\nc\ne\n"


def test_strip_optional_blocks_no_markers_is_noop():
    text = "no markers here\njust text\n"
    assert template.strip_optional_blocks(text, enabled=False) == text
    assert template.strip_optional_blocks(text, enabled=True) == text


def test_strip_optional_blocks_marker_with_surrounding_whitespace():
    text = (
        "x\n"
        "   # ccpkg:vault:start  \n"
        "inner\n"
        "\t<!-- ccpkg:vault:end -->\n"
        "y\n"
    )
    disabled = template.strip_optional_blocks(text, enabled=False)
    assert disabled == "x\ny\n"
    enabled = template.strip_optional_blocks(text, enabled=True)
    assert enabled == "x\ninner\ny\n"


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def test_render_substitutes_then_strips_when_vault_disabled():
    text = (
        "root=${CODE_ROOT}\n"
        "# ccpkg:vault:start\n"
        "vault=${VAULT_ROOT}\n"
        "# ccpkg:vault:end\n"
        "end\n"
    )
    out = template.render(text, make_vars(), vault_enabled=False)
    assert out == "root=/home/me/Documents/Code\nend\n"


def test_render_substitutes_then_keeps_content_when_vault_enabled():
    text = (
        "root=${CODE_ROOT}\n"
        "# ccpkg:vault:start\n"
        "vault=${VAULT_ROOT}\n"
        "# ccpkg:vault:end\n"
        "end\n"
    )
    out = template.render(text, make_vars(), vault_enabled=True)
    assert out == (
        "root=/home/me/Documents/Code\n"
        "vault=/home/me/Vault\n"
        "end\n"
    )


def test_render_equals_strip_of_substitute():
    text = (
        "a ${AWS_PROFILE}\n"
        "<!-- ccpkg:vault:start -->\n"
        "v ${VAULT_ROOT}\n"
        "<!-- ccpkg:vault:end -->\n"
    )
    vars_ = make_vars()
    for enabled in (True, False):
        expected = template.strip_optional_blocks(
            template.substitute(text, vars_), enabled
        )
        assert template.render(text, vars_, enabled) == expected


# ---------------------------------------------------------------------------
# reverse_substitute
# ---------------------------------------------------------------------------

def test_reverse_substitute_replaces_values_with_var_refs():
    vars_ = make_vars()
    text = "lives at /home/me/Documents/Code using profile acme-dev"
    out = template.reverse_substitute(text, vars_)
    assert out == "lives at ${CODE_ROOT} using profile ${AWS_PROFILE}"


def test_reverse_substitute_does_not_reverse_home():
    vars_ = make_vars(home="/home/me")
    text = "path /home/me/notes"
    out = template.reverse_substitute(text, vars_)
    # HOME must NOT be reversed.
    assert out == "path /home/me/notes"


def test_reverse_substitute_longest_value_first():
    # CODE_ROOT is a prefix-containing value relative to HOME; with VAULT_ROOT a
    # longer overlapping value, the longest must win and not be partially eaten.
    vars_ = {
        "HOME": "/home/me",
        "CODE_ROOT": "/home/me/code",
        "VAULT_ROOT": "/home/me/code/vault",
        "AWS_PROFILE": "",
    }
    text = "v=/home/me/code/vault c=/home/me/code"
    out = template.reverse_substitute(text, vars_)
    assert out == "v=${VAULT_ROOT} c=${CODE_ROOT}"


def test_reverse_substitute_skips_empty_values():
    vars_ = make_vars(vault_root="", aws_profile="")
    text = "code=/home/me/Documents/Code vault= aws="
    out = template.reverse_substitute(text, vars_)
    # empty values must not turn every empty span into ${VAULT_ROOT}/${AWS_PROFILE}.
    assert out == "code=${CODE_ROOT} vault= aws="


def test_reverse_substitute_only_handles_three_named_vars():
    vars_ = {
        "HOME": "/home/me",
        "CODE_ROOT": "/home/me/Documents/Code",
        "VAULT_ROOT": "/home/me/Vault",
        "AWS_PROFILE": "acme-dev",
        "EXTRA": "should-not-be-reversed",
    }
    text = "extra=should-not-be-reversed vault=/home/me/Vault"
    out = template.reverse_substitute(text, vars_)
    assert out == "extra=should-not-be-reversed vault=${VAULT_ROOT}"


# ---------------------------------------------------------------------------
# round-trip: substitute then reverse_substitute
# ---------------------------------------------------------------------------

def test_round_trip_substitute_then_reverse():
    vars_ = make_vars()
    original = (
        "code=${CODE_ROOT}\n"
        "vault=${VAULT_ROOT}\n"
        "aws=${AWS_PROFILE}\n"
    )
    rendered = template.substitute(original, vars_)
    assert "${" not in rendered
    back = template.reverse_substitute(rendered, vars_)
    assert back == original


def test_round_trip_vault_strip_on_off_with_render():
    vars_ = make_vars()
    text = (
        "keep ${CODE_ROOT}\n"
        "# ccpkg:vault:start\n"
        "optional ${VAULT_ROOT}\n"
        "# ccpkg:vault:end\n"
    )
    enabled = template.render(text, vars_, vault_enabled=True)
    disabled = template.render(text, vars_, vault_enabled=False)
    assert enabled == "keep /home/me/Documents/Code\noptional /home/me/Vault\n"
    assert disabled == "keep /home/me/Documents/Code\n"
    # reversing the enabled render restores the var refs (vault content survives).
    back = template.reverse_substitute(enabled, vars_)
    assert back == "keep ${CODE_ROOT}\noptional ${VAULT_ROOT}\n"
