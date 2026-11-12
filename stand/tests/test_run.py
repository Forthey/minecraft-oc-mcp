import json
from dataclasses import replace

from stand.config import load_config
from stand.runner.agents import AgentCfg
from stand.runner.run import find_scenario, run_one

AGENT = AgentCfg(name="x", cmd=["true"], skills_dir=None, mcp_format="claude_json", usage_parser="none")


def test_real_mode_skips_fake_only_scenario(tmp_path):
    cfg = replace(load_config(), robot_mcp="real", real={"command": ["team-mcp"]})
    run_dir = run_one(cfg, find_scenario("s05-connection-lost"), AGENT, runs_dir=tmp_path)
    results = json.loads((run_dir / "results.json").read_text())
    assert results["status"] == "SKIPPED" and "fake" in results["reason"]
    assert (run_dir / "report.md").exists()
    assert "s05-connection-lost" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_find_scenario_by_id_and_path():
    s = find_scenario("s01-wall")
    assert find_scenario(str(s.path)).id == "s01-wall"
