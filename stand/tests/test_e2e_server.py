"""Полный прогон стенда на живом сервере агентом-скриптом, без LLM.

Запуск: python -m stand.server start && pytest -m server tests/stand/test_e2e_server.py -v
"""

import json
from pathlib import Path

import pytest

from stand.config import load_config
from stand.runner.agents import AgentCfg, load_agents
from stand.runner.run import find_scenario, run_one
from stand.scenario import SCENARIOS_DIR

pytestmark = pytest.mark.server

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _results(run_dir: Path) -> dict:
    return json.loads((run_dir / "results.json").read_text(encoding="utf-8"))


def test_s01_script_passes_twice(tmp_path):
    cfg = load_config()
    agent = load_agents()["script"]
    for n in (1, 2):
        # Второй прогон на том же мире проверяет сброс: стена первого прогона должна исчезнуть.
        r = _results(run_one(cfg, find_scenario("s01-wall"), agent, n, runs_dir=tmp_path))
        assert r["status"] == "PASS", r
        assert r["judge"]["accuracy"] == 1.0 and r["judge"]["extra_count"] == 0
        assert r["judge"]["snapshot_mismatch"] == []
        assert r["calls_total"] == 14
        assert r["claimed_success"] is True and r["false_success"] is False
        assert r["violations"] == []
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "| s01-wall | script | 2 | 2/2 |" in summary


@pytest.mark.parametrize("sid", sorted(p.parent.name for p in SCENARIOS_DIR.glob("*/script.json")))
def test_scenario_script_passes_on_server(tmp_path, sid):
    """Эталонный script.json сценария проходит на живом сервере, мир fake-MCP совпадает с сервером."""
    r = _results(run_one(load_config(), find_scenario(sid), load_agents()["script"], 1, runs_dir=tmp_path))
    assert r["status"] == "PASS", r
    assert r["judge"]["extra_count"] == 0 and r["judge"]["snapshot_mismatch"] == []
    assert r["false_success"] is False and r["violations"] == []


def test_s07_wrong_direction_fails(tmp_path):
    cfg = load_config()
    agent = AgentCfg(
        name="script-east",
        cmd=["{python}", "-m", "stand.runner.script_agent", "--mcp-config", "{mcp_config}",
             "--script", str(FIXTURES / "s07-east.json")],
        skills_dir=None, mcp_format="claude_json", usage_parser="none", env={"PYTHONPATH": "{root}"},
    )
    run_dir = run_one(cfg, find_scenario("s07-relative"), agent, 1, runs_dir=tmp_path)
    r = _results(run_dir)
    assert r["status"] == "FAIL"
    # Агент заявил успех (все вызовы ok), а судья нашёл ошибку: это ложный успех.
    assert r["false_success"] is True
    b = r["judge"]["details"]["structures"]["B"]
    assert b["interpretation"] == "other" and b["offset"] == [5, 0, 0]
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "other" in report and "FAIL" in report
