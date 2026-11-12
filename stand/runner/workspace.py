"""Рабочая папка агента вне репозитория.

Агент не должен видеть ответ: stand/scenarios с expected и stand/knowledge. Поэтому
папка создаётся во временном каталоге системы, а fake-MCP получает копию сценария
без expected, которая лежит в private/ папки прогона.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from stand.config import ROOT, Config, render_real_command
from stand.runner.agents import AgentCfg
from stand.scenario import Scenario
from stand.server.setup import mod_versions

SKILLS_DIR = ROOT / "agent" / "skills"
MCP_NAME = "robot"
AGENTS_MD = (
    "# Robot goals\n\n"
    "For any goal about the OpenComputers robot in Minecraft, follow "
    "skills/oc-orchestrator/SKILL.md. Robot tools come from the MCP server named robot.\n"
)


@dataclass
class Workspace:
    """Готовая рабочая папка: путь, конфиг MCP (если файлом) и аргументы MCP (если строкой)."""

    path: Path
    mcp_config: Path | None
    mcp_args: list[str] = field(default_factory=list)
    harness: dict = field(default_factory=dict)

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def sanitized_scenario(s: Scenario, private_dir: Path) -> Path:
    """Копия сценария для fake-MCP без expected и scoring."""
    data = dict(s.raw)
    data["expected"] = {"mode": "fixed", "fill": []}
    data.pop("scoring", None)
    private_dir.mkdir(parents=True, exist_ok=True)
    path = private_dir / "mcp_scenario.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def mcp_server_spec(python: str, scenario: str, log: str, profile: str | None, root: str) -> dict:
    """Описание stdio-сервера fake-MCP: команда, аргументы, окружение."""
    args = ["-m", "stand.fake_mcp", "--scenario", scenario, "--log", log, "--world", "rcon"]
    if profile:
        args += ["--profile", profile]
    return {"command": python, "args": args, "env": {"PYTHONPATH": root}}


def _server_spec(run_dir: Path, s: Scenario, cfg: Config, profile: str | None) -> dict:
    if cfg.robot_mcp == "real":
        if cfg.real.get("command"):
            # Агенту виден путь к сценарию в конфиге MCP, поэтому в команду идёт очищенный сценарий.
            scenario = sanitized_scenario(s, run_dir / "private")
            cmd = render_real_command(cfg, scenario, run_dir / "action_log.jsonl")
            return {"command": cmd[0], "args": cmd[1:], "env": {"PYTHONPATH": str(ROOT)}}
        if cfg.real.get("url"):
            return {"url": cfg.real["url"]}
        raise ValueError("robot_mcp is real, set real.command or real.url in stand/config.yaml")
    scenario = sanitized_scenario(s, run_dir / "private")
    return mcp_server_spec(sys.executable, str(scenario), str(run_dir / "action_log.jsonl"), profile, str(ROOT))


def _harness(s: Scenario, cfg: Config) -> dict:
    versions = mod_versions(cfg.mods_manifest)
    return {
        "versions": {
            "minecraft": "1.7.10",
            "ic2": versions.get("ic2", ""),
            "opencomputers": versions.get("opencomputers", ""),
        },
        "warehouse": {"pos": list(s.warehouse["pos"]), "side": s.warehouse["side"]},
        "autonomy": "auto",
        "budgets": {
            "step_attempts": 3,
            "stage_redelegations": 2,
            "design_revisions": 1,
            "research_sources": 6,
            "robot_calls_per_stage": 150,
        },
        # Подтверждать гейты некому: прогон идёт без человека.
        "safety": {"require_confirm": []},
        "research": {"sources": ["rag", "web", "model"], "cache_dir": ".oc-knowledge"},
    }


# Codex по умолчанию ждёт ответа tool 60 с, а move_to по длинному пути идёт дольше.
CODEX_TOOL_TIMEOUT_S = 600


def codex_mcp_args(spec: dict, name: str = MCP_NAME) -> list[str]:
    """Флаги -c, которыми Codex получает stdio MCP-сервер без правки ~/.codex/config.toml.

    Значения -c разбираются как TOML. Строка JSON с экранированием подходит как
    базовая строка TOML, в том числе для путей Windows с обратными слешами.
    """
    out = ["-c", f"mcp_servers.{name}.command={json.dumps(spec['command'])}",
           "-c", f"mcp_servers.{name}.args={json.dumps(spec['args'])}",
           "-c", f"mcp_servers.{name}.tool_timeout_sec={CODEX_TOOL_TIMEOUT_S}"]
    for key, val in spec.get("env", {}).items():
        out += ["-c", f"mcp_servers.{name}.env.{key}={json.dumps(val)}"]
    return out


def _codex_args(spec: dict) -> list[str]:
    # Подтверждать вызовы некому: прогон идёт без человека.
    return codex_mcp_args(spec) + ["-c", 'approval_policy="never"']


def build_workspace(
    run_dir: Path,
    s: Scenario,
    agent: AgentCfg,
    cfg: Config,
    profile: str | None = None,
) -> Workspace:
    """Создаёт рабочую папку агента: скиллы, oc-harness.yaml, конфиг MCP."""
    run_dir.mkdir(parents=True, exist_ok=True)
    ws = Path(tempfile.mkdtemp(prefix="oc-stand-"))
    skills_rel = agent.skills_dir or "skills"
    shutil.copytree(SKILLS_DIR, ws / skills_rel)
    # Claude Code находит скиллы сам. Codex и opencode получают явную ссылку из AGENTS.md.
    if agent.mcp_format != "claude_json":
        (ws / "AGENTS.md").write_text(AGENTS_MD.replace("skills/", f"{skills_rel}/"), encoding="utf-8")
    harness = _harness(s, cfg)
    (ws / "oc-harness.yaml").write_text(yaml.safe_dump(harness, sort_keys=False, allow_unicode=True), encoding="utf-8")

    spec = _server_spec(run_dir, s, cfg, profile)
    if agent.mcp_format == "claude_json":
        server = dict(spec, type="http") if "url" in spec else spec
        path = ws / "mcp.json"
        path.write_text(json.dumps({"mcpServers": {MCP_NAME: server}}, indent=2), encoding="utf-8")
        return Workspace(ws, path, harness=harness)
    if agent.mcp_format == "opencode_json":
        if "url" in spec:
            server = {"type": "remote", "url": spec["url"]}
        else:
            server = {"type": "local", "command": [spec["command"], *spec["args"]], "environment": spec["env"]}
        (ws / "opencode.json").write_text(json.dumps({"mcp": {MCP_NAME: server}}, indent=2), encoding="utf-8")
        return Workspace(ws, None, harness=harness)
    if agent.mcp_format == "codex_args":
        if "url" in spec:
            args = ["-c", f"mcp_servers.{MCP_NAME}.url={json.dumps(spec['url'])}", "-c", 'approval_policy="never"']
        else:
            args = _codex_args(spec)
        return Workspace(ws, None, args, harness=harness)
    raise ValueError(f"unknown mcp_format {agent.mcp_format}")
