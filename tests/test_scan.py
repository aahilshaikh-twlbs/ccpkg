import os

from ccpkg import scan
from ccpkg.scan import (
    Finding,
    SECRET_FILES,
    scan_text_secrets,
    scan_text_purity,
    load_purity_terms,
    scan_paths,
    is_clean,
)


# ---- scan_text_secrets: positive ----

def test_secret_openai_key_detected():
    findings = scan_text_secrets("token = sk-abcdEFGH0123456789ZZ\n", "f.py")
    assert len(findings) == 1
    assert findings[0].rule == "secret"
    assert findings[0].path == "f.py"
    assert findings[0].line == 1


def test_secret_github_pat_detected():
    findings = scan_text_secrets("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    assert len(findings) == 1
    assert findings[0].rule == "secret"


def test_secret_aws_access_key_detected():
    findings = scan_text_secrets("key: AKIAIOSFODNN7EXAMPLE")
    assert len(findings) == 1
    assert findings[0].rule == "secret"


def test_secret_private_key_header_detected():
    findings = scan_text_secrets("-----BEGIN RSA PRIVATE KEY-----")
    assert len(findings) == 1
    assert findings[0].rule == "secret"


def test_secret_authorization_keyword_detected():
    findings = scan_text_secrets('"authorization": "Bearer x"')
    assert len(findings) == 1
    assert findings[0].rule == "secret"


def test_secret_reports_correct_line_number():
    text = "line one\nline two\ntok = sk-abcdEFGH0123456789ZZ\n"
    findings = scan_text_secrets(text, "multi.txt")
    assert len(findings) == 1
    assert findings[0].line == 3


# ---- scan_text_secrets: negative ----

def test_secret_clean_text_no_findings():
    findings = scan_text_secrets("just a normal config line\nno keys here\n", "ok.txt")
    assert findings == []


def test_secret_short_sk_prefix_not_matched():
    # sk- with fewer than 16 trailing chars must not match
    findings = scan_text_secrets("sk-tooShort")
    assert findings == []


# ---- scan_text_purity: positive ----

def test_purity_term_hit():
    findings = scan_text_purity("we use AcmeCorp internally\n",
                                ["acmecorp"], "doc.md")
    assert len(findings) == 1
    assert findings[0].rule == "purity"
    assert findings[0].path == "doc.md"
    assert findings[0].line == 1


def test_purity_case_insensitive():
    findings = scan_text_purity("WIDGETCO project", ["widgetco"])
    assert len(findings) == 1
    assert findings[0].rule == "purity"


def test_purity_users_path_hit():
    findings = scan_text_purity("cmd = /Users/example/bin/x\n", [], "h.sh")
    assert len(findings) == 1
    assert findings[0].rule == "purity"
    assert findings[0].line == 1


def test_purity_home_path_hit():
    findings = scan_text_purity("path = /home/ubuntu/.claude", [])
    assert len(findings) == 1
    assert findings[0].rule == "purity"


def test_purity_templated_home_path_not_flagged():
    # $HOME-relative paths are clean; only literal /Users/ /home/ trip the rule
    findings = scan_text_purity("path = $HOME/.claude/x", ["acmecorp"])
    assert findings == []


def test_purity_home_path_skipped_when_disabled():
    # check_home_paths=False: literal home paths are NOT flagged (used for non-base
    # files where fictional /home//Users fixtures are legitimate).
    findings = scan_text_purity("cmd = /Users/example/bin/x\n", [],
                                "h.sh", check_home_paths=False)
    assert findings == []


# ---- scan_text_purity: negative ----

def test_purity_clean_text_no_findings():
    findings = scan_text_purity("generic portable content\n",
                                ["acmecorp", "widgetco"], "ok.md")
    assert findings == []


# ---- load_purity_terms ----

def test_load_purity_terms_defaults_only(tmp_path):
    # No real PII is hardcoded: with no .ccpkg/purity-terms.txt, defaults are empty.
    terms = load_purity_terms(str(tmp_path))
    assert terms == list(scan.DEFAULT_PURITY_TERMS)
    assert scan.DEFAULT_PURITY_TERMS == []


def test_load_purity_terms_appends_file_lines(tmp_path):
    ccpkg_dir = os.path.join(str(tmp_path), ".ccpkg")
    os.makedirs(ccpkg_dir)
    with open(os.path.join(ccpkg_dir, "purity-terms.txt"), "w") as fh:
        fh.write("acmecorp\n\n# comment\nwidgetco\n")
    terms = load_purity_terms(str(tmp_path))
    assert "acmecorp" in terms
    assert "widgetco" in terms
    assert "# comment" not in terms
    assert "" not in terms


# ---- scan_paths ----

def test_scan_paths_secrets_always_both_layers(tmp_path):
    p = os.path.join(str(tmp_path), "leak.txt")
    with open(p, "w") as fh:
        fh.write("tok = sk-abcdEFGH0123456789ZZ\n")
    base = scan_paths([p], "base", ["acmecorp"])
    overlay = scan_paths([p], "overlay", ["acmecorp"])
    assert any(f.rule == "secret" for f in base)
    assert any(f.rule == "secret" for f in overlay)


def test_scan_paths_purity_base_only(tmp_path):
    p = os.path.join(str(tmp_path), "doc.md")
    with open(p, "w") as fh:
        fh.write("we love acmecorp\n")
    base = scan_paths([p], "base", ["acmecorp"])
    overlay = scan_paths([p], "overlay", ["acmecorp"])
    assert any(f.rule == "purity" for f in base)
    # overlay is EXEMPT from purity
    assert all(f.rule != "purity" for f in overlay)


def test_scan_paths_overlay_still_blocks_secrets_not_purity(tmp_path):
    p = os.path.join(str(tmp_path), "mix.txt")
    with open(p, "w") as fh:
        fh.write("acmecorp\ntok = sk-abcdEFGH0123456789ZZ\n")
    overlay = scan_paths([p], "overlay", ["acmecorp"])
    assert any(f.rule == "secret" for f in overlay)
    assert all(f.rule != "purity" for f in overlay)


def test_scan_paths_secret_file_basename_is_finding(tmp_path):
    # a SECRET_FILES basename is a finding regardless of (empty/clean) content
    assert ".credentials.json" in SECRET_FILES
    p = os.path.join(str(tmp_path), ".credentials.json")
    with open(p, "w") as fh:
        fh.write("")
    findings = scan_paths([p], "base", [])
    assert any(f.rule == "secret" and f.path == p for f in findings)


def test_scan_paths_clean_file_no_findings(tmp_path):
    p = os.path.join(str(tmp_path), "clean.md")
    with open(p, "w") as fh:
        fh.write("totally portable generic content\n")
    findings = scan_paths([p], "base", ["acmecorp", "widgetco"])
    assert findings == []


# ---- repo_shippable_files ----

def test_repo_shippable_files_excludes_vcs_venv_private_ccpkg(tmp_path):
    root = str(tmp_path)
    # shippable files
    os.makedirs(os.path.join(root, "ccpkg"))
    with open(os.path.join(root, "README.md"), "w") as fh:
        fh.write("doc\n")
    with open(os.path.join(root, "ccpkg", "scan.py"), "w") as fh:
        fh.write("code\n")
    # excluded dirs (handoffs/ is gitignored local-only session docs — must not be scanned)
    for excluded in (".git", ".venv", ".pytest_cache", "__pycache__", "private", ".ccpkg", "handoffs"):
        os.makedirs(os.path.join(root, excluded))
        with open(os.path.join(root, excluded, "ignored.txt"), "w") as fh:
            fh.write("nope\n")

    found = scan.repo_shippable_files(root)
    rels = sorted(os.path.relpath(p, root) for p in found)
    assert rels == ["README.md", os.path.join("ccpkg", "scan.py")]


# ---- scan_repo ----

def test_scan_repo_flags_home_path_in_non_home_base_file(tmp_path):
    # F2: the un-templated home-path regex now applies to ALL base files, not
    # only those under home/.claude. A literal /Users/<name> path in a docs/ (or
    # root) file is flagged. Previously check_home_paths was gated on home/.claude
    # membership, so this exact case slipped through.
    root = str(tmp_path)
    docs = os.path.join(root, "docs")
    os.makedirs(docs)
    guide = os.path.join(docs, "guide.md")
    with open(guide, "w") as fh:
        fh.write("clone and run from /Users/someone/Code/x\n")
    findings = scan.scan_repo(root, [])
    assert any(f.rule == "purity" and f.detail == "/Users/someone"
               and f.path == guide for f in findings)


def test_scan_repo_still_clean_for_templated_paths(tmp_path):
    # $HOME-relative paths in a non-home base file must NOT trip the home-path
    # rule — only literal /Users//home do.
    root = str(tmp_path)
    with open(os.path.join(root, "README.md"), "w") as fh:
        fh.write('run python3 "$HOME/.claude/mboard/hooks/x.py"\n')
    findings = scan.scan_repo(root, [])
    assert all(f.rule != "purity" for f in findings)


# ---- is_clean ----

def test_is_clean_true_on_empty():
    assert is_clean([]) is True


def test_is_clean_false_on_findings():
    assert is_clean([Finding(path="x", line=1, rule="secret", detail="d")]) is False
