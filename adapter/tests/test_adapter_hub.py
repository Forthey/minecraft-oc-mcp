import json
import threading
import time
import urllib.request

import anyio
from adapter_harness import free_port, make_sim
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from robot_double import RobotDouble

from adapter import hub
from adapter.__main__ import main


def test_local_upstream_with_robot_double(tmp_path):
    port = free_port()
    bridge = hub.make_bridge(port=port, log_file=tmp_path / "bridge.log", world_id="stand")
    server = bridge.start_http_server()
    double = RobotDouble(make_sim(), f"http://127.0.0.1:{port}")
    double.start()
    up = hub.LocalUpstream(bridge)

    async def go():
        names = {t["name"] for t in await up.list_tools()}
        return names, await up.call("turn", {"direction": "left"}), await up.call("move", {"direction": "sideways"}), \
            await up.call("inventory_transfer", {"from_slot": 1, "to_slot": 2})

    try:
        names, turned, bad, failed = anyio.run(go)
    finally:
        double.stop()
        server.shutdown()
    assert "move" in names
    assert turned[0] is True
    assert bad[0] is False and bad[1].startswith("bad argument: ") and bad[2] == "BLOCKED"
    assert failed[0] is False and failed[2] == "NO_ITEM"


def _wait_http(url: str, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(url)


def test_serve_http_mcp_and_installer(tmp_path):
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    argv = ["serve", "--port", str(port), "--bridge-log", str(tmp_path / "bridge.log"), "--world-id", "stand"]
    thread = threading.Thread(target=main, args=(argv,), daemon=True)
    thread.start()
    _wait_http(base + "/get.lua")
    with urllib.request.urlopen(base + "/get.lua", timeout=2) as r:
        installer = r.read().decode()
    assert f"wget -fq {base}/oc_mcp/tools/move.lua" in installer
    with urllib.request.urlopen(base + "/oc_mcp/tools/move.lua", timeout=2) as r:
        assert r.status == 200
    double = RobotDouble(make_sim(), base)
    double.start()

    async def go():
        async with streamable_http_client(base + "/mcp") as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                result = await session.call_tool("move", {"direction": "up"})
                return names, json.loads(result.content[0].text)

    try:
        names, env = anyio.run(go)
    finally:
        double.stop()
    assert {"move", "move_to", "get_action_log"} <= names
    assert env["ok"] is True and "message" in env


def test_installer_passes_non_default_url():
    from adapter import robot_files

    text = robot_files.installer("http://10.0.0.5:9000", "http://10.0.0.5:9000").decode()
    assert '"oc_mcp http://10.0.0.5:9000\\n"' in text
    assert '"oc_mcp\\n"' in robot_files.installer("http://h:1").decode()
