import os
import sys
import time
from pathlib import Path

import pytest

from stand.runner import agents as agents_mod
from stand.runner.agents import AGENTS_PATH, AgentCfg, load_agents, render_cmd, run_agent


def test_agents_yaml_loads():
    agents = load_agents(AGENTS_PATH)
    assert {"claude", "codex", "opencode"} <= set(agents)
    for a in agents.values():
        assert a.mcp_format in {"claude_json", "opencode_json", "codex_args"}
        assert a.cmd


def test_render_cmd_placeholders(tmp_path, monkeypatch):
    monkeypatch.setattr(agents_mod.shutil, "which", lambda name: f"/bin/{name}")
    a = AgentCfg(name="x", cmd=["tool", "-p", "{prompt}", "--cfg", "{mcp_config}", "{mcp_args}", "--cd", "{workspace}"],
                 skills_dir=None, mcp_format="codex_args", usage_parser="none")
    cmd = render_cmd(a, "build it", tmp_path / "mcp.json", tmp_path, mcp_args=["-c", "a=1"])
    assert cmd == ["/bin/tool", "-p", "build it", "--cfg", str(tmp_path / "mcp.json"), "-c", "a=1", "--cd", str(tmp_path)]


def test_render_cmd_resolves_cmd_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(agents_mod.shutil, "which", lambda name: "C:\\npm\\claude.cmd")
    a = AgentCfg(name="claude", cmd=["claude", "-p", "{prompt}"], skills_dir=None, mcp_format="claude_json",
                 usage_parser="none")
    assert render_cmd(a, "go", tmp_path / "m.json", tmp_path)[0] == "C:\\npm\\claude.cmd"


def test_render_cmd_missing_executable(tmp_path, monkeypatch):
    monkeypatch.setattr(agents_mod.shutil, "which", lambda name: None)
    a = AgentCfg(name="nope", cmd=["nope-agent"], skills_dir=None, mcp_format="claude_json", usage_parser="none")
    with pytest.raises(FileNotFoundError, match="nope-agent"):
        render_cmd(a, "go", tmp_path / "m.json", tmp_path)


def test_run_agent_captures_output(tmp_path):
    run = run_agent([sys.executable, "-c", "print('hello'); import sys; sys.exit(3)"], tmp_path, 30,
                    tmp_path / "t.jsonl", tmp_path / "err.log")
    assert run.exit_code == 3 and not run.timed_out
    assert (tmp_path / "t.jsonl").read_text().strip() == "hello"


def _alive(pid):
    if sys.platform == "win32":
        import subprocess
        return str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # Зомби считается мёртвым: проверяем состояние в /proc, если он есть.
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().split()[2] == "Z")


def test_run_agent_timeout_kills_tree(tmp_path):
    pidfile = tmp_path / "child.pid"
    code = (
        "import subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open(r'{pidfile}', 'w').write(str(p.pid))\n"
        "time.sleep(60)\n"
    )
    start = time.monotonic()
    run = run_agent([sys.executable, "-c", code], tmp_path, 3, tmp_path / "t.jsonl", tmp_path / "err.log")
    assert run.timed_out
    assert time.monotonic() - start < 20
    child = int(pidfile.read_text())
    deadline = time.monotonic() + 5
    while _alive(child) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _alive(child)
