"""Режим real с адаптером: подстановки в real.command и источник журнала действий."""

import sys
from dataclasses import replace
from pathlib import Path

from stand.config import load_config, render_real_command
from stand.runner.run import action_log_source

ADAPTER_CMD = ["{python}", "-m", "adapter", "--oc-mcp", "{oc_mcp_dir}/bridge/server.py",
               "--map", "stand.adapter_map:oracle", "--map-arg", "scenario={scenario}", "--log", "{action_log}"]


def test_render_real_command_placeholders():
    cfg = replace(load_config(), robot_mcp="real", real={"command": ADAPTER_CMD}, oc_mcp_dir=Path("/x/oc-mcp"))
    cmd = render_real_command(cfg, Path("/runs/1/private/s.yaml"), Path("/runs/1/action_log.jsonl"))
    # Подстановки это str(Path), на Windows с обратными слешами.
    assert cmd == [sys.executable, "-m", "adapter", "--oc-mcp", f"{Path('/x/oc-mcp')}/bridge/server.py",
                   "--map", "stand.adapter_map:oracle", "--map-arg", f"scenario={Path('/runs/1/private/s.yaml')}",
                   "--log", str(Path("/runs/1/action_log.jsonl"))]


def test_runner_uses_adapter_log_file():
    base = load_config()
    assert action_log_source(replace(base, robot_mcp="fake")) == "fake"
    assert action_log_source(replace(base, robot_mcp="real", real={"command": ADAPTER_CMD})) == "adapter"
    assert action_log_source(replace(base, robot_mcp="real", real={"command": ["team-mcp"]})) == "get_action_log"
