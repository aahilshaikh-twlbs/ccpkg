import os
import shutil
import subprocess

import pytest

from ccpkg import config

REPO = config.repo_root()
FORMULA = os.path.join(REPO, "Formula", "ccpkg.rb")

# The exact set the formula copies into libexec — must all exist at the repo root.
RUNTIME_SUBSET = ["ccpkg", "manifest.json", "home", "mailbox", "install.sh", "LICENSE"]


def test_runtime_subset_exists_at_repo_root():
    missing = [p for p in RUNTIME_SUBSET if not os.path.exists(os.path.join(REPO, p))]
    assert missing == [], "formula install-set missing from repo: %s" % missing


def test_formula_file_present():
    assert os.path.isfile(FORMULA), "Formula/ccpkg.rb not found"


def test_formula_declares_expected_stanzas():
    with open(FORMULA, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert 'url "https://github.com/aahilshaikh-twlbs/ccpkg/archive/refs/tags/v' in text
    assert "sha256" in text
    assert 'license "MIT"' in text
    assert 'depends_on "python@3.12"' in text
    assert 'depends_on "jq"' in text
    assert "CCPKG_ROOT" in text
    # every runtime-subset entry must be named in the libexec.install line
    for entry in RUNTIME_SUBSET:
        assert '"%s"' % entry in text, "formula does not install %s" % entry


def test_formula_ccpkg_root_uses_stable_opt_prefix():
    # CCPKG_ROOT must resolve to the version-independent opt prefix, not the
    # versioned Cellar keg. With #{libexec} (Cellar), every `brew upgrade` deletes
    # the old keg and dangles every symlink ccpkg lays into ~/.claude until the
    # user re-runs `ccpkg install`. #{opt_libexec} survives upgrades.
    with open(FORMULA, "r", encoding="utf-8") as fh:
        text = fh.read()
    assert 'CCPKG_ROOT="#{opt_libexec}"' in text
    assert 'CCPKG_ROOT="#{libexec}"' not in text


def test_formula_ruby_syntax_valid():
    ruby = shutil.which("ruby")
    if ruby is None:
        pytest.skip("ruby not available to syntax-check the formula")
    result = subprocess.run([ruby, "-c", FORMULA], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
