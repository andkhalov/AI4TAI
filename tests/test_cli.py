"""bin/ai4tai.py: разбор .env, построение флагов расширений, алиасы моделей, doctor без .env."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def cli():
    spec = importlib.util.spec_from_file_location("ai4tai_cli", REPO / "bin" / "ai4tai.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_load_env_handles_quotes_pipes_and_comments(cli, tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "# comment\n\nYANDEX_CLOUD_API_KEY=abc\nTARU_API=\"1194|hash=with=equals\"\n"
        "SINGLE='q'\nNOEQ\nSPACED = v \n",
        encoding="utf-8",
    )
    env = cli.load_env(p)
    assert env["YANDEX_CLOUD_API_KEY"] == "abc"
    assert env["TARU_API"] == "1194|hash=with=equals"
    assert env["SINGLE"] == "q"
    assert env["SPACED"] == "v"
    assert "NOEQ" not in env


def test_load_env_missing_file(cli, tmp_path):
    assert cli.load_env(tmp_path / "nope") == {}


def test_resolve_model_aliases(cli):
    assert cli.resolve_model("") == cli.DEFAULT_MODEL
    assert cli.resolve_model("qwen") == "qwen3.6-35b-a3b/latest"
    assert cli.resolve_model("deepseek-v4-flash/latest") == "deepseek-v4-flash/latest"
    assert cli.resolve_model("gpt-oss-120b") == "gpt-oss-120b/latest"


def test_build_goose_ext_args(cli):
    exts = [
        {"type": "builtin", "name": "developer"},
        {"type": "stdio", "name": "ai4tai", "cmd": "bin/ai4tai-mcp", "args": []},
        {"type": "stdio", "name": "my", "cmd": "/abs/python", "args": ["/abs/tool.py"]},
    ]
    args = cli.build_goose_ext_args(exts)
    assert args[:2] == ["--with-builtin", "developer"]
    assert args[2] == "--with-extension"
    assert str(REPO / "bin" / "ai4tai-mcp") in args[3]
    if cli.IS_WINDOWS:
        assert args[3].endswith(".bat'") or args[3].endswith(".bat")
    assert "/abs/tool.py" in args[5]


def test_recipe_parses(cli):
    instructions, extensions = cli.parse_recipe()
    assert "AI4TAI" in instructions
    names = [e["name"] for e in extensions]
    assert "developer" in names and "ai4tai" in names
    for e in extensions:
        if e.get("type") == "stdio":
            shim = REPO / e["cmd"]
            assert shim.exists(), f"shim из recipe не найден: {shim}"


def test_help_runs(cli):
    rc = subprocess.run([sys.executable, str(REPO / "bin" / "ai4tai.py"), "--help"],
                        capture_output=True, text=True, encoding="utf-8")
    assert rc.returncode == 0
    assert "AI4TAI" in rc.stdout


def test_doctor_without_env_exits_1(cli, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ENV_FILE", tmp_path / ".env")
    with pytest.raises(SystemExit) as ei:
        cli.doctor()
    assert ei.value.code == 1


def test_probe_mcp_lists_tools(cli):
    """Реальный запуск MCP-сервера через shim: ≥10 инструментов, без сети (mock)."""
    tools, err = cli.probe_mcp(env_vars={"AI4TAI_SITE_MODE": "mock"}, timeout=25)
    assert err == "", err
    assert tools is not None and len(tools) >= cli.MIN_TOOLS
    for name in ("site_search", "sqlite_query", "rag_search", "web_search", "load_skill"):
        assert name in tools
