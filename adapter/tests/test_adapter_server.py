"""Адаптер целиком: conformance стенда, s01 агентом-скриптом, плагин карты, CLI."""

import json
import subprocess
import sys
from types import SimpleNamespace

import anyio
from conftest import bridge, make_sim

from adapter.__main__ import load_map
from adapter.action_log import ActionLog
from adapter.robot import RobotAdapter
from adapter.tools import ADDITION_SPECS
from stand.adapter_map import SnapshotMap, memory_snapshot
from stand.conformance.checks import load_scene, run_checks
from stand.scenario import SCENARIOS_DIR

ROOT = SCENARIOS_DIR.parents[1]


class AdapterSession:
    """Сессия MCP в процессе поверх RobotAdapter, как DispatcherSession в tests/stand/test_conformance.py."""

    def __init__(self, ad, upstream_tools):
        self.ad = ad
        self.names = [t["name"] for t in upstream_tools] + list(ADDITION_SPECS)

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name=n) for n in self.names])

    async def call_tool(self, name, arguments=None):
        env = await self.ad.call(name, arguments or {})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(env))], is_error=False)


def _map(sim):
    return SnapshotMap(sim.region, sim.k, lambda: memory_snapshot(sim.world, sim.region), sim.world)


def test_conformance_against_adapter(tmp_path):
    scene = load_scene()
    sim = make_sim(str(scene["scenario_path"]))

    async def go():
        async with bridge(sim, tmp_path) as up:
            ad = RobotAdapter(up, _map(sim), ActionLog(None))
            await ad.start()
            return await run_checks(AdapterSession(ad, await up.list_tools()), scene)

    results = anyio.run(go)
    assert all(r.ok for r in results), [r for r in results if not r.ok]
    assert len(results) == 7


def test_s01_script_through_adapter(tmp_path):
    sim = make_sim(inventory=[])
    script = json.loads((SCENARIOS_DIR / "s01-wall" / "script.json").read_text(encoding="utf-8"))

    async def go():
        async with bridge(sim, tmp_path) as up:
            ad = RobotAdapter(up, _map(sim), ActionLog(tmp_path / "action_log.jsonl"))
            await ad.start()
            return [await ad.call(c["tool"], c["args"]) for c in script]

    envs = anyio.run(go)
    assert all(e["ok"] for e in envs), [e for e in envs if not e["ok"]]
    wall = [(x, y, 100) for y in (64, 65, 66) for x in (100, 101, 102)]
    assert all(sim.world.get(p) == ("minecraft:cobblestone", 0) for p in wall)
    assert envs[-1]["data"]["missing"] == [] and envs[-1]["data"]["wrong"] == []
    assert len((tmp_path / "action_log.jsonl").read_text().splitlines()) == len(script)


def test_load_map_plugin(monkeypatch):
    import stand.adapter_map as plugin

    monkeypatch.setattr(plugin, "oracle", lambda scenario: ("map", scenario))
    assert load_map("stand.adapter_map:oracle", ["scenario=x.yaml"]) == ("map", "x.yaml")
    assert load_map(None, []).available is False


def test_cli_help():
    r = subprocess.run([sys.executable, "-m", "adapter", "--help"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and "--oc-mcp" in r.stdout


def test_adapter_process_over_stdio(tmp_path):
    """python -m adapter как отдельный процесс: агентская MCP-сессия, мост, тестовый робот."""
    from conftest import free_port, oc_mcp_server
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from robot_double import RobotDouble

    sim = make_sim(inventory=[{"item": "minecraft:cobblestone", "count": 9}])
    port = free_port()
    double = RobotDouble(sim, f"http://127.0.0.1:{port}")
    args = ["-m", "adapter", "--oc-mcp", str(oc_mcp_server()), "--port", str(port),
            "--bridge-log", str(tmp_path / "bridge.log"), "--log", str(tmp_path / "action_log.jsonl")]

    async def go():
        params = StdioServerParameters(command=sys.executable, args=args, cwd=str(ROOT),
                                       env={"PYTHONPATH": str(ROOT)})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                result = await session.call_tool("get_status", {})
                return names, json.loads(result.content[0].text)

    double.start()
    try:
        names, status = anyio.run(go)
    finally:
        double.stop()
    assert len(names) == 28 and {"place_at", "nei_find"} <= names
    assert status["ok"] and status["data"]["pos"] == [100, 64, 105]
    assert json.loads((tmp_path / "action_log.jsonl").read_text().splitlines()[0])["tool"] == "get_status"
