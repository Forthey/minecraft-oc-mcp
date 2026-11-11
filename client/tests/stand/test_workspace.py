import json
from dataclasses import replace

import pytest
import yaml

from stand.config import ROOT, load_config
from stand.runner.agents import AgentCfg
from stand.runner.workspace import build_workspace, mcp_server_spec, sanitized_scenario
from stand.scenario import SCENARIOS_DIR, load_scenario

CLAUDE = AgentCfg(name="claude", cmd=["claude"], skills_dir=".claude/skills", mcp_format="claude_json",
                  usage_parser="claude_stream_json")
CODEX = AgentCfg(name="codex", cmd=["codex"], skills_dir=None, mcp_format="codex_args", usage_parser="codex_json")
OPENCODE = AgentCfg(name="opencode", cmd=["opencode"], skills_dir=".opencode/skills", mcp_format="opencode_json",
                    usage_parser="none")


@pytest.fixture
def s01():
    return load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml")


def test_workspace_outside_repo(tmp_path, s01):
    ws = build_workspace(tmp_path / "run", s01, CLAUDE, load_config())
    assert not ws.path.resolve().is_relative_to(ROOT)
    ws.cleanup()
    assert not ws.path.exists()


def test_workspace_claude(tmp_path, s01):
    ws = build_workspace(tmp_path / "run", s01, CLAUDE, load_config())
    p = ws.path
    assert (p / ".claude/skills/oc-orchestrator/SKILL.md").exists()
    assert (p / ".claude/skills/references/tool-contract.md").exists()
    harness = yaml.safe_load((p / "oc-harness.yaml").read_text(encoding="utf-8"))
    assert harness["autonomy"] == "auto"
    assert harness["safety"]["require_confirm"] == []
    assert harness["warehouse"] == {"pos": [95, 64, 105], "side": "east"}
    assert harness["versions"]["ic2"] == "2.2.828-experimental"
    cfg = json.loads(ws.mcp_config.read_text(encoding="utf-8"))
    server = cfg["mcpServers"]["robot"]
    assert server["env"]["PYTHONPATH"] == str(ROOT)
    assert "--scenario" in server["args"]
    ws.cleanup()


def test_mcp_scenario_has_no_answer(tmp_path, s01):
    """Fake-MCP получает копию сценария без expected: агент не найдёт там ответа."""
    ws = build_workspace(tmp_path / "run", s01, CLAUDE, load_config())
    args = json.loads(ws.mcp_config.read_text())["mcpServers"]["robot"]["args"]
    path = args[args.index("--scenario") + 1]
    data = yaml.safe_load(open(path, encoding="utf-8"))
    assert data["expected"] == {"mode": "fixed", "fill": []}
    assert "stand/scenarios" not in path.replace("\\", "/")
    ws.cleanup()


def test_sanitized_scenario_still_loads(tmp_path):
    s = load_scenario(SCENARIOS_DIR / "s07-relative" / "scenario.yaml")
    path = sanitized_scenario(s, tmp_path)
    back = load_scenario(path)
    assert back.robot == s.robot and back.warehouse == s.warehouse
    assert back.expected == {"mode": "fixed", "fill": []}


def test_workspace_codex_agents_md(tmp_path, s01):
    ws = build_workspace(tmp_path / "run", s01, CODEX, load_config())
    assert (ws.path / "skills/oc-orchestrator/SKILL.md").exists()
    assert "skills/oc-orchestrator/SKILL.md" in (ws.path / "AGENTS.md").read_text(encoding="utf-8")
    assert ws.mcp_config is None
    assert any(a.startswith("mcp_servers.robot.command=") for a in ws.mcp_args)
    assert "approval_policy=\"never\"" in ws.mcp_args
    ws.cleanup()


def test_workspace_opencode(tmp_path, s01):
    ws = build_workspace(tmp_path / "run", s01, OPENCODE, load_config())
    cfg = json.loads((ws.path / "opencode.json").read_text(encoding="utf-8"))
    robot = cfg["mcp"]["robot"]
    assert robot["type"] == "local" and robot["command"][1:3] == ["-m", "stand.fake_mcp"]
    assert robot["environment"]["PYTHONPATH"] == str(ROOT)
    assert (ws.path / "AGENTS.md").exists()
    ws.cleanup()


def test_mcp_config_windows_paths():
    spec = mcp_server_spec(python="C:\\Python\\python.exe", scenario="C:\\stand\\s01\\scenario.yaml",
                           log="C:\\runs\\a.jsonl", profile=None, root="C:\\repo")
    text = json.dumps({"mcpServers": {"robot": spec}})
    back = json.loads(text)["mcpServers"]["robot"]
    assert back["args"][back["args"].index("--scenario") + 1] == "C:\\stand\\s01\\scenario.yaml"
    assert back["env"]["PYTHONPATH"] == "C:\\repo"


def test_profile_override_passed(tmp_path, s01):
    ws = build_workspace(tmp_path / "run", s01, CLAUDE, load_config(), profile="no-docs")
    args = json.loads(ws.mcp_config.read_text())["mcpServers"]["robot"]["args"]
    assert args[args.index("--profile") + 1] == "no-docs"
    ws.cleanup()


def test_real_mode_uses_team_server(tmp_path, s01):
    cfg = replace(load_config(), robot_mcp="real", real={"command": ["team-mcp", "--port", "1"], "url": None})
    ws = build_workspace(tmp_path / "run", s01, CLAUDE, cfg)
    server = json.loads(ws.mcp_config.read_text())["mcpServers"]["robot"]
    assert server["command"] == "team-mcp" and server["args"] == ["--port", "1"]
    ws.cleanup()
