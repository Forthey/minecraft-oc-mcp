"""Один прогон сценария агентом: сброс, сцена, агент, снимок, судья, результаты."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import anyio

from stand.config import ROOT, Config
from stand.judge import judge
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.rcon import Rcon
from stand.runner import report
from stand.runner.agents import AgentCfg, render_cmd, render_env, run_agent
from stand.runner.metrics import collect
from stand.runner.usage import parse_usage, robot_calls
from stand.runner.reset import ensure_server, full_reset, prepare_scene, reset_region
from stand.runner.workspace import build_workspace
from stand.scenario import SCENARIOS_DIR, Scenario, load_scenario
from stand.world.backend import RconWorld, WorldBackend
from stand.world.registry import load_item_ids
from stand.world.snapshot import Snapshot, capture

RUNS_DIR = ROOT / "stand" / "runs"
SPOT_CHECKS = 5


def find_scenario(name: str) -> Scenario:
    """Сценарий по id из stand/scenarios или по пути к файлу."""
    path = Path(name)
    if not path.exists():
        path = SCENARIOS_DIR / name / "scenario.yaml"
    return load_scenario(path)


def _rcon(cfg: Config) -> Rcon:
    return Rcon(cfg.rcon_host, cfg.rcon_port, cfg.rcon_password, timeout=30)


def prepare(cfg: Config, scenario: Scenario, k: Knowledge, fresh: bool = False) -> None:
    """Сервер запущен, регион чистый, сцена поставлена. При неудачном сбросе делает полный."""
    ensure_server(cfg)
    if fresh:
        full_reset(cfg)
    for attempt in range(2):
        with _rcon(cfg) as rcon:
            world = RconWorld(rcon)
            clean = reset_region(world, lambda: capture(rcon, cfg.world_dir, scenario.region), scenario, k)
            if clean:
                prepare_scene(world, scenario, k, load_item_ids(cfg.world_dir / "level.dat"))
                return
        if attempt == 0:
            full_reset(cfg)
    raise RuntimeError(f"region of {scenario.id} is not clean even after a full reset")


def spot_check(world: WorldBackend, snap: Snapshot, k: Knowledge, n: int = SPOT_CHECKS) -> list[dict]:
    """Сверяет несколько клеток снимка с миром через testforblock. Пустой список значит совпало."""
    cells = sorted(snap.changed().items())
    sample = random.Random(0).sample(cells, min(n, len(cells)))
    return [
        {"pos": list(p), "snapshot": f"{b[0]}:{b[1]}"}
        for p, b in sample
        if not world.test_block(p, b, any_meta=k.meta_mask(b[0]) != 15)
    ]


def evaluate(cfg: Config, scenario: Scenario, k: Knowledge, run_dir: Path | None = None) -> dict:
    """Снимок региона и вердикт судьи. Если задан run_dir, пишет snapshot.json и judge.json."""
    with _rcon(cfg) as rcon:
        snap = capture(rcon, cfg.world_dir, scenario.region)
        mismatch = spot_check(RconWorld(rcon), snap, k)
    result = judge(snap, scenario, k)
    result["snapshot_mismatch"] = mismatch
    if run_dir is not None:
        (run_dir / "snapshot.json").write_text(json.dumps(snap.to_json()), encoding="utf-8")
        (run_dir / "judge.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


async def _fetch_real_log(cfg: Config) -> list[dict]:
    from stand.conformance.checks import connect, parse_envelope

    async with connect("real", cfg) as session:
        env = parse_envelope(await session.call_tool("get_action_log", {"last_n": 1000}))
    if not env["ok"]:
        raise RuntimeError(env.get("error_code"))
    return env["data"].get("actions", [])


def action_log_source(cfg: Config) -> str:
    """Откуда берётся журнал действий прогона.

    fake: fake-MCP пишет его сам. adapter: real.command с {action_log}, адаптер пишет
    файл прогона, а новое подключение подняло бы новый адаптер с пустым журналом.
    get_action_log: сервер команды отдаёт журнал через tool после прогона.
    """
    if cfg.robot_mcp != "real":
        return "fake"
    if any("{action_log}" in str(a) for a in cfg.real.get("command") or []):
        return "adapter"
    return "get_action_log"


def fetch_real_action_log(cfg: Config, path: Path) -> str | None:
    """Забирает action log реального сервера. Возвращает текст ошибки или None."""
    try:
        actions = anyio.run(_fetch_real_log, cfg)
    except Exception as e:  # noqa: BLE001 - отсутствие лога не должно ронять прогон
        return f"{type(e).__name__}: {e}"
    with open(path, "w", encoding="utf-8") as f:
        for a in actions:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    return None


def run_one(
    cfg: Config,
    scenario: Scenario,
    agent: AgentCfg,
    n: int = 1,
    fresh: bool = False,
    profile: str | None = None,
    runs_dir: Path = RUNS_DIR,
    keep_workspace: bool = False,
) -> Path:
    """Полный прогон. Возвращает папку прогона с results.json."""
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{scenario.id}-{agent.name}-{n}"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id, "scenario": scenario.id, "agent": agent.name, "n": n,
        "robot_mcp": cfg.robot_mcp, "profile": profile or scenario.profile,
        "started": datetime.now().isoformat(timespec="seconds"),
    }

    if cfg.robot_mcp == "real" and "fake" in scenario.requires:
        report.write(run_dir, {**meta, "status": "SKIPPED", "reason": "scenario requires fake MCP"})
        report.write_summary(runs_dir)
        return run_dir

    k = Knowledge.load(KNOWLEDGE_DIR, scenario.knowledge)
    prepare(cfg, scenario, k, fresh)

    ws = build_workspace(run_dir, scenario, agent, cfg, profile)
    try:
        if cfg.robot_mcp == "real" and cfg.real.get("real_setup"):
            subprocess.run([*cfg.real["real_setup"], str(scenario.path)], check=True)
        prompt = cfg.prompt_template.format(goal=scenario.goal)
        cmd = render_cmd(agent, prompt, ws.mcp_config, ws.path, ws.mcp_args, scenario.path.parent)
        meta["cmd"] = cmd
        agent_run = run_agent(cmd, ws.path, scenario.timeout_s, run_dir / "transcript.jsonl",
                              run_dir / "agent_stderr.log", render_env(agent))
        tasks = ws.path / ".oc-tasks"
        if tasks.exists():
            shutil.copytree(tasks, run_dir / "journal", dirs_exist_ok=True)
    finally:
        if keep_workspace:
            meta["workspace"] = str(ws.path)
        else:
            ws.cleanup()

    judge_result = evaluate(cfg, scenario, k, run_dir)
    source = action_log_source(cfg)
    if source == "adapter":
        meta["action_log_source"] = "adapter"
        if not (run_dir / "action_log.jsonl").exists():
            meta["action_log_error"] = "adapter did not write action_log.jsonl"
    elif source == "get_action_log":
        error = fetch_real_action_log(cfg, run_dir / "action_log.jsonl")
        if error:
            meta["action_log_error"] = error
    if cfg.robot_mcp == "real" and meta.get("action_log_error"):
        calls = robot_calls(agent.usage_parser, run_dir / "transcript.jsonl")
        with open(run_dir / "action_log.jsonl", "w", encoding="utf-8") as f:
            for c in calls:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        meta["action_log_source"] = "transcript"
    usage = parse_usage(agent.usage_parser, run_dir / "transcript.jsonl")
    metrics = collect(run_dir, scenario, k, judge_result, agent_run, usage, ws.harness, agent.usage_parser)
    report.write(run_dir, {**meta, **metrics})
    report.write_summary(runs_dir)
    return run_dir
