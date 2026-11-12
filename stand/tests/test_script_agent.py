import json
import re
import subprocess
import sys
from pathlib import Path

from stand.config import ROOT
from stand.runner.agents import load_agents, render_cmd
from stand.scenario import SCENARIOS_DIR
from tools.validate_skills import JOURNAL_LINE_RE

S01_SCRIPT = SCENARIOS_DIR / "s01-wall" / "script.json"


def _mcp_config(tmp_path, scenario: Path) -> Path:
    spec = {
        "command": sys.executable,
        "args": ["-m", "stand.fake_mcp", "--scenario", str(scenario), "--world", "memory",
                 "--log", str(tmp_path / "action_log.jsonl")],
        "env": {"PYTHONPATH": str(ROOT)},
    }
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"robot": spec}}), encoding="utf-8")
    return path


def _run(tmp_path, script: Path, scenario: Path):
    cmd = [sys.executable, "-m", "stand.runner.script_agent", "--mcp-config", str(_mcp_config(tmp_path, scenario)),
           "--script", str(script)]
    return subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True, timeout=120,
                          env={"PYTHONPATH": str(ROOT), "PATH": ""})


def _journal(tmp_path) -> list[str]:
    return (tmp_path / ".oc-tasks" / "script" / "journal.md").read_text(encoding="utf-8").splitlines()


def test_script_agent_memory(tmp_path):
    r = _run(tmp_path, S01_SCRIPT, SCENARIOS_DIR / "s01-wall" / "scenario.yaml")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = _journal(tmp_path)
    assert all(JOURNAL_LINE_RE.match(line) for line in lines)
    assert re.search(r"phase=final .* status=DONE", lines[-1])
    log = [json.loads(line) for line in (tmp_path / "action_log.jsonl").read_text().splitlines()]
    assert len(log) == 14 and all(e["ok"] for e in log)
    assert [e["tool"] for e in log[:4]] == ["move_to", "face", "storage_scan", "storage_take"]
    assert sum(1 for e in log if e["tool"] == "place_at") == 9
    assert log[-1]["tool"] == "verify_blocks"


def test_script_agent_reports_failure(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"tool": "move_to", "args": {"x": 500, "y": 64, "z": 500}}]), encoding="utf-8")
    r = _run(tmp_path, bad, SCENARIOS_DIR / "s01-wall" / "scenario.yaml")
    assert r.returncode == 1
    assert "OUT_OF_RANGE" in r.stdout
    assert "status=FAILED" in _journal(tmp_path)[-1]


def test_script_agent_fails_on_verify_diff(tmp_path):
    """verify_blocks с пропусками считается провалом, даже если сам вызов ok."""
    script = tmp_path / "verify.json"
    script.write_text(json.dumps([{"tool": "verify_blocks", "args": {"expected": [
        {"pos": [100, 64, 100], "item": "minecraft:cobblestone"}]}}]), encoding="utf-8")
    r = _run(tmp_path, script, SCENARIOS_DIR / "s01-wall" / "scenario.yaml")
    assert r.returncode == 1 and "missing" in r.stdout


def test_script_agent_entry_renders(tmp_path):
    a = load_agents()["script"]
    cmd = render_cmd(a, "ignored", tmp_path / "mcp.json", tmp_path, scenario_dir=SCENARIOS_DIR / "s01-wall")
    assert cmd[0] == sys.executable
    assert cmd[cmd.index("--script") + 1] == str(S01_SCRIPT)


def test_script_agent_expected_error(tmp_path):
    """Шаг с expect должен вернуть этот код. Тогда скрипт идёт дальше, иначе это провал."""
    s01 = SCENARIOS_DIR / "s01-wall" / "scenario.yaml"
    far = {"tool": "move_to", "args": {"x": 500, "y": 64, "z": 500}}
    script = tmp_path / "expect.json"
    script.write_text(json.dumps([{**far, "expect": "OUT_OF_RANGE"}, {"tool": "get_status", "args": {}}]))
    r = _run(tmp_path, script, s01)
    assert r.returncode == 0, r.stdout
    assert re.search(r"phase=final .* status=DONE delta=2/2", _journal(tmp_path)[-1])

    script.write_text(json.dumps([{**far, "expect": "NO_PATH"}]))
    r = _run(tmp_path, script, s01)
    assert r.returncode == 1 and "expected NO_PATH, got OUT_OF_RANGE" in r.stdout

    script.write_text(json.dumps([{"tool": "get_status", "args": {}, "expect": "NO_PATH"}]))
    r = _run(tmp_path, script, s01)
    assert r.returncode == 1 and "expected NO_PATH, got ok" in r.stdout
