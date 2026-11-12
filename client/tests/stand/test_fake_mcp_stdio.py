"""Сквозная проверка: fake-MCP поднимается как stdio-сервер и отвечает клиенту MCP."""

import json
import sys
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from stand.scenario import SCENARIOS_DIR

ROOT = Path(__file__).resolve().parents[2]


async def _roundtrip(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "stand.fake_mcp", "--scenario", str(SCENARIOS_DIR / "s01-wall" / "scenario.yaml"),
              "--log", str(tmp_path / "log.jsonl"), "--world", "memory"],
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("get_status", {})
            return tools, result


def test_stdio_roundtrip(tmp_path):
    tools, result = anyio.run(_roundtrip, tmp_path)
    names = {t.name for t in tools.tools}
    assert len(names) == 28
    place_at = next(t for t in tools.tools if t.name == "place_at")
    assert set(place_at.input_schema["required"]) == {"x", "y", "z", "item"}
    envelope = json.loads(result.content[0].text)
    assert envelope["ok"] is True
    assert envelope["data"]["pos"] == [100, 64, 105]
    assert (tmp_path / "log.jsonl").read_text(encoding="utf-8").count("\n") == 1
