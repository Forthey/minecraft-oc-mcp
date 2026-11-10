import json
from dataclasses import replace

from stand.config import load_config
from stand.runner.agents import AgentCfg, AgentRun
from stand.runner.run import basic_results, find_scenario, run_one

AGENT = AgentCfg(name="x", cmd=["true"], skills_dir=None, mcp_format="claude_json", usage_parser="none")


def test_real_mode_skips_fake_only_scenario(tmp_path):
    cfg = replace(load_config(), robot_mcp="real", real={"command": ["team-mcp"]})
    run_dir = run_one(cfg, find_scenario("s05-connection-lost"), AGENT, runs_dir=tmp_path)
    results = json.loads((run_dir / "results.json").read_text())
    assert results["status"] == "SKIPPED" and "fake" in results["reason"]


def test_basic_results_statuses():
    meta = {"run_id": "r"}
    assert basic_results(meta, AgentRun(0, True, 5.0), None)["status"] == "TIMEOUT"
    assert basic_results(meta, AgentRun(0, False, 5.0), {"passed": True})["status"] == "PASS"
    assert basic_results(meta, AgentRun(1, False, 5.0), {"passed": False})["status"] == "FAIL"


def test_find_scenario_by_id_and_path():
    s = find_scenario("s01-wall")
    assert find_scenario(str(s.path)).id == "s01-wall"
