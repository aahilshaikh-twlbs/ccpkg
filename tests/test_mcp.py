import json
import os

import pytest

from ccpkg import cli, mcp, scan, config


# --- catalog integrity -------------------------------------------------------

def test_catalog_ids_unique_and_nonempty():
    ids = mcp.catalog_ids()
    assert len(ids) == len(set(ids))
    assert len(ids) >= 10


@pytest.mark.parametrize("srv", mcp.MCP_CATALOG, ids=lambda s: s.id)
def test_every_entry_is_well_formed(srv):
    entry = srv.entry()
    if srv.transport == "stdio":
        assert entry["command"]
        assert isinstance(entry["args"], list)
    else:
        assert entry["type"] in ("http", "sse")
        assert entry["url"].startswith("https://")


def test_token_servers_use_var_placeholders_not_literals():
    gh = mcp.by_id()["github"]
    entry = gh.entry()
    # value is a ${VAR} reference, never a real token
    name = "GITHUB_PERSONAL_ACCESS_TOKEN"
    assert entry["env"][name] == "${" + name + "}"
    assert name in gh.referenced_vars()


def test_catalog_module_is_scan_clean():
    # the catalog source itself must pass the secret + purity scan
    root = config.repo_root()
    src = os.path.join(root, "ccpkg", "mcp.py")
    text = open(src, encoding="utf-8").read()
    terms = scan.load_purity_terms(root)
    assert not scan.scan_text_secrets(text, src)
    assert not scan.scan_text_purity(text, terms, src)


# --- apply_servers: deep-merge + idempotency ---------------------------------

def test_apply_creates_mcp_json(tmp_path):
    path = mcp.mcp_json_path(str(tmp_path))
    result = mcp.apply_servers(["github", "linear"], path)
    assert result["added"] == ["github", "linear"]
    doc = json.load(open(path))
    assert set(doc["mcpServers"]) == {"github", "linear"}
    assert doc["mcpServers"]["linear"] == {"type": "http", "url": "https://mcp.linear.app/mcp"}


def test_apply_preserves_existing_servers(tmp_path):
    path = mcp.mcp_json_path(str(tmp_path))
    # a user-authored server already in the file
    with open(path, "w") as fh:
        json.dump({"mcpServers": {"my-own": {"command": "foo", "args": []}}}, fh)
    mcp.apply_servers(["github"], path)
    doc = json.load(open(path))
    assert "my-own" in doc["mcpServers"]      # preserved
    assert "github" in doc["mcpServers"]      # added


def test_apply_is_idempotent(tmp_path):
    path = mcp.mcp_json_path(str(tmp_path))
    mcp.apply_servers(["stripe"], path)
    first = open(path).read()
    result = mcp.apply_servers(["stripe"], path)
    assert result["added"] == []
    assert result["present"] == ["stripe"]
    assert open(path).read() == first        # byte-identical re-run


def test_apply_reports_env_vars(tmp_path):
    path = mcp.mcp_json_path(str(tmp_path))
    result = mcp.apply_servers(["github", "brave-search"], path)
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in result["vars"]
    assert "BRAVE_API_KEY" in result["vars"]


def test_load_corrupt_file_is_empty(tmp_path):
    path = mcp.mcp_json_path(str(tmp_path))
    open(path, "w").write("{ not json")
    assert mcp.load(path) == {}


# --- CLI wiring --------------------------------------------------------------

def test_cli_mcp_list(capsys):
    rc = cli.main(["mcp", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "github" in out and "linear" in out
    assert "add: ccpkg mcp add" in out


def test_cli_mcp_add_writes_cwd(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["mcp", "add", "github"])
    assert rc == 0
    doc = json.load(open(tmp_path / ".mcp.json"))
    assert "github" in doc["mcpServers"]
    out = capsys.readouterr().out
    assert "GITHUB_PERSONAL_ACCESS_TOKEN" in out


def test_cli_mcp_add_unknown_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["mcp", "add", "not-a-server"])
    assert rc == 2
    assert "unknown server" in capsys.readouterr().err
    assert not (tmp_path / ".mcp.json").exists()   # nothing written on error


def test_cli_mcp_add_no_names_errors(capsys):
    rc = cli.main(["mcp", "add"])
    assert rc == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_cli_mcp_no_action_errors(capsys):
    rc = cli.main(["mcp"])
    assert rc == 2


# --- the completions mcp feed ------------------------------------------------

def test_completions_mcp_feed(capsys):
    rc = cli.main(["completions", "mcp"])
    assert rc == 0
    names = [ln for ln in capsys.readouterr().out.splitlines() if ln]
    assert set(names) == set(mcp.catalog_ids())
