import copy
import json
from types import SimpleNamespace

import anyio
import pytest

from stand.config import load_config
from stand.conformance.checks import CONFORMANCE_DIR, connect, load_scene, run_checks
from stand.fake_mcp.action_log import ActionLog
from stand.fake_mcp.dispatch import TOOL_SPECS, Dispatcher
from stand.fake_mcp.envelope import ok
from stand.fake_mcp.sim import RobotSim
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import check_scenario, load_scenario
from stand.world.backend import MemoryWorld


class DispatcherSession:
    """Сессия MCP поверх Dispatcher в том же процессе: так можно подменять поведение сервера."""

    def __init__(self, dispatcher, tools=None):
        self.d = dispatcher
        self.tools = tools

    async def list_tools(self):
        names = self.tools if self.tools is not None else self.d.enabled_tools()
        return SimpleNamespace(tools=[SimpleNamespace(name=n) for n in names])

    async def call_tool(self, name, arguments=None):
        env = self.d.call(name, arguments or {})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(env))], is_error=False)


def _dispatcher():
    scene = load_scene()
    s = copy.deepcopy(load_scenario(scene["scenario_path"]))
    sim = RobotSim(s, Knowledge.load(KNOWLEDGE_DIR), MemoryWorld(s.scene_blocks()))
    return Dispatcher(sim, "full", [], ActionLog(None))


def _run(session):
    return anyio.run(run_checks, session, load_scene())


def test_scene_scenario_valid():
    scene = load_scene()
    s = load_scenario(scene["scenario_path"])
    assert check_scenario(s, Knowledge.load(KNOWLEDGE_DIR), load_config()) == []
    # Робот смотрит на склад: сторона occupied_side занята сундуком, empty_slot в нём пуст.
    assert scene["occupied_side"] == scene["warehouse_side"] == "front"
    assert s.robot["facing"] == "west" and tuple(s.robot["pos"]) == (96, 64, 105)
    assert tuple(s.warehouse["pos"]) == (95, 64, 105)


def test_inprocess_fake_passes():
    results = _run(DispatcherSession(_dispatcher()))
    assert all(r.ok for r in results), [r for r in results if not r.ok]
    assert {r.name for r in results} == {
        "tools_match_contract", "envelope_shape", "blocked_on_occupied",
        "no_item_on_empty_slot", "out_of_range", "unknown_item", "nei_available",
    }


def test_fake_passes_conformance_over_stdio():
    async def go():
        async with connect("fake", load_config()) as session:
            return await run_checks(session, load_scene())

    results = anyio.run(go)
    assert all(r.ok for r in results), [r for r in results if not r.ok]


def test_broken_server_detected(monkeypatch):
    d = _dispatcher()
    monkeypatch.setattr(d.sim, "place", lambda *a, **kw: ok("placed"))
    results = {r.name: r for r in _run(DispatcherSession(d))}
    assert not results["blocked_on_occupied"].ok
    assert "BLOCKED" in results["blocked_on_occupied"].detail
    assert results["out_of_range"].ok


def test_missing_tool_detected():
    d = _dispatcher()
    tools = [n for n in TOOL_SPECS if n != "verify_blocks"]
    results = {r.name: r for r in _run(DispatcherSession(d, tools=tools))}
    assert not results["tools_match_contract"].ok
    assert "verify_blocks" in results["tools_match_contract"].detail


def test_malformed_envelope_detected(monkeypatch):
    d = _dispatcher()
    monkeypatch.setattr(d.sim, "get_status", lambda: {"position": [1, 2, 3]})
    results = {r.name: r for r in _run(DispatcherSession(d))}
    assert not results["envelope_shape"].ok


def test_unknown_error_code_detected(monkeypatch):
    d = _dispatcher()
    from stand.fake_mcp.envelope import err

    monkeypatch.setattr(d.sim, "place_at", lambda *a, **kw: err("NOT_FOUND", "no such item"))
    results = {r.name: r for r in _run(DispatcherSession(d))}
    assert not results["unknown_item"].ok
    assert "NOT_FOUND" in results["unknown_item"].detail


def test_cli_exit_code(capsys):
    from stand.conformance.__main__ import main

    assert main(["--mcp", "fake"]) == 0
    out = capsys.readouterr().out
    assert "tools_match_contract" in out and "7/7" in out


def test_no_provider_counts_as_nei_available():
    sim_d = _dispatcher()
    d = Dispatcher(sim_d.sim, "no-nei", [], ActionLog(None))
    results = {r.name: r for r in _run(DispatcherSession(d))}
    assert results["nei_available"].ok and "NO_PROVIDER" in results["nei_available"].detail


def test_real_without_config_explains():
    """В stand/config.yaml секция real пустая: понятная ошибка вместо падения."""
    from stand.conformance.__main__ import main

    with pytest.raises(SystemExit, match="real.command"):
        main(["--mcp", "real"])
