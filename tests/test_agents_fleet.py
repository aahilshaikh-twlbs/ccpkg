import re
from pathlib import Path

from ccpkg import manifest, scan

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / "home" / ".claude" / "agents"
NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.M)


def _agent_items():
    items = manifest.parse(str(ROOT / "manifest.json"))
    return [i for i in items if i.group == "Agents"]


def _frontmatter_name(text):
    assert text.startswith("---\n"), "missing frontmatter"
    end = text.index("\n---", 4)
    m = NAME_RE.search(text[4:end])
    assert m, "no name in frontmatter"
    return m.group(1)


def test_fleet_has_38_base_symlink_items():
    items = _agent_items()
    assert len(items) == 38
    for i in items:
        assert i.layer == "base"
        assert i.mode == "symlink"
        assert i.os == "any"
        assert i.desc.strip(), "{0} has empty desc".format(i.path)


def test_recommended_core_agents_are_default_on():
    core = {"agents/debugger.md", "agents/reviewer.md", "agents/architect.md",
            "agents/tester.md", "agents/refactor.md", "agents/researcher.md",
            "agents/implementer.md"}
    items = _agent_items()
    on = {i.path for i in items if i.default}
    assert on == core, "default-on set drifted: {0}".format(sorted(on))
    # everything else stays opt-in
    assert all(i.default is False for i in items if i.path not in core)


def test_every_item_has_a_file_with_matching_bare_name():
    for i in _agent_items():
        stem = Path(i.path).stem
        f = ROOT / "home" / ".claude" / i.path
        assert f.is_file(), "missing {0}".format(i.path)
        name = _frontmatter_name(f.read_text())
        assert name == stem, "{0}: frontmatter name {1} != stem".format(i.path, name)
        assert "aahil" not in name.lower()


def test_no_orphan_files_outside_manifest():
    on_disk = {p.name for p in AGENTS_DIR.glob("*.md")}
    in_manifest = {Path(i.path).name for i in _agent_items()}
    assert on_disk == in_manifest


def test_every_agent_file_is_scan_clean():
    terms = scan.load_purity_terms(str(ROOT))
    for f in sorted(AGENTS_DIR.glob("*.md")):
        text = f.read_text()
        findings = scan.scan_text_purity(text, terms, str(f), check_home_paths=True)
        assert not findings, "{0}: {1}".format(f.name, [x.detail for x in findings])
        assert "{{include:" not in text and "[[" not in text
        assert "aahil" not in text.lower()
