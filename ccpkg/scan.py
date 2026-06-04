import os
import re
from dataclasses import dataclass
from typing import List

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{16,}",
    r"ghp_[A-Za-z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\"?(authorization|bearer|access_token|refresh_token|client_secret)\"?\s*[:=]",
]
SECRET_FILES = [".credentials.json", ".claude.json"]

# Real company/person/product terms are NEVER hardcoded here (this file ships in
# the public base). They live in the gitignored <root>/.ccpkg/purity-terms.txt,
# loaded at runtime by load_purity_terms().
DEFAULT_PURITY_TERMS = []  # type: List[str]

_HOME_PATH_PATTERNS = [r"/Users/[^/\s]+", r"/home/[^/\s]+"]

_SECRET_RES = [re.compile(p, re.IGNORECASE) for p in SECRET_PATTERNS]
_HOME_PATH_RES = [re.compile(p) for p in _HOME_PATH_PATTERNS]


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    detail: str


def scan_text_secrets(text, path=""):
    # type: (str, str) -> List[Finding]
    findings = []  # type: List[Finding]
    for lineno, line in enumerate(text.splitlines(), start=1):
        for regex in _SECRET_RES:
            match = regex.search(line)
            if match:
                findings.append(Finding(path=path, line=lineno, rule="secret",
                                        detail=match.group(0)))
                break
    return findings


def scan_text_purity(text, terms, path="", check_home_paths=True):
    # type: (str, List[str], str, bool) -> List[Finding]
    lowered_terms = [t.lower() for t in terms]
    findings = []  # type: List[Finding]
    for lineno, line in enumerate(text.splitlines(), start=1):
        lowered_line = line.lower()
        for term in lowered_terms:
            if term and term in lowered_line:
                findings.append(Finding(path=path, line=lineno, rule="purity",
                                        detail=term))
                break
        else:
            if not check_home_paths:
                continue
            for regex in _HOME_PATH_RES:
                match = regex.search(line)
                if match:
                    findings.append(Finding(path=path, line=lineno, rule="purity",
                                            detail=match.group(0)))
                    break
    return findings


def load_purity_terms(root):
    # type: (str) -> List[str]
    terms = list(DEFAULT_PURITY_TERMS)
    path = os.path.join(root, ".ccpkg", "purity-terms.txt")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh.read().splitlines():
                stripped = raw.strip()
                if stripped and not stripped.startswith("#"):
                    terms.append(stripped)
    return terms


def scan_paths(paths, layer, terms, check_home_paths=True):
    # type: (List[str], str, List[str], bool) -> List[Finding]
    findings = []  # type: List[Finding]
    for path in paths:
        if os.path.basename(path) in SECRET_FILES:
            findings.append(Finding(path=path, line=0, rule="secret",
                                    detail="secret file: " + os.path.basename(path)))
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except (IOError, OSError):
            continue
        findings.extend(scan_text_secrets(text, path))
        if layer == "base":
            findings.extend(
                scan_text_purity(text, terms, path, check_home_paths=check_home_paths)
            )
    return findings


# Directories never swept by the repo-wide scan: VCS metadata, virtualenvs,
# caches, the gitignored private overlay, and the local-only purity-terms config.
_SCAN_EXCLUDE_DIRS = frozenset([
    ".git", ".venv", ".pytest_cache", "__pycache__", "private", ".ccpkg",
])


def repo_shippable_files(root):
    # type: (str) -> List[str]
    """Walk `root` and return every shippable file, excluding VCS/venv/cache dirs,
    the gitignored private/ overlay, and the local-only .ccpkg/ config. Stdlib only."""
    out = []  # type: List[str]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SCAN_EXCLUDE_DIRS]
        for name in filenames:
            out.append(os.path.join(dirpath, name))
    return out


def _is_under(path, parent):
    # type: (str, str) -> bool
    return path == parent or path.startswith(parent + os.sep)


def scan_repo(root, terms):
    # type: (str, List[str]) -> List[Finding]
    """Repo-wide sweep of every shippable file (Contract §8, broadened).

    Policy per file:
      - base source-of-truth (home/.claude): secrets + purity terms + the
        un-templated home-path regex (the live-applied managed files must never
        leak a literal /Users//home path).
      - the scanner's own test suite (tests/): purity terms ONLY — these files
        legitimately carry synthetic secret-shaped and home-path fixtures that
        exist to exercise the detectors; they must still be free of real
        company/person terms.
      - everything else: secrets + purity terms (no home-path regex, so fictional
        example paths in docs/configs do not false-positive).
    """
    base_src = os.path.join(root, "home", ".claude")
    tests_dir = os.path.join(root, "tests")
    findings = []  # type: List[Finding]
    for path in repo_shippable_files(root):
        if _is_under(path, tests_dir):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except (IOError, OSError):
                continue
            findings.extend(
                scan_text_purity(text, terms, path, check_home_paths=False)
            )
            continue
        check_home_paths = _is_under(path, base_src)
        findings.extend(
            scan_paths([path], "base", terms, check_home_paths=check_home_paths)
        )
    return findings


def is_clean(findings):
    # type: (List[Finding]) -> bool
    return not findings
