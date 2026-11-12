"""Связь с oc-mcp: дочерний процесс bridge/server.py и MCP-сессия по stdio.

Адаптер единственный клиент моста: мост держит HTTP-порт для робота в одном
экземпляре, поэтому второй процесс с ним работать не может.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError

# Код JSON-RPC, которым мост отвечает на неверные аргументы и неизвестный tool.
INVALID_PARAMS = -32602


def bridge_cmd(server_py: Path, python: str, port: int, log_file: Path | None, world_id: str | None) -> list[str]:
    """Команда запуска моста oc-mcp."""
    cmd = [python, str(server_py), "--port", str(port)]
    if log_file is not None:
        cmd += ["--log-file", str(log_file)]
    if world_id:
        cmd += ["--world-id", world_id]
    return cmd


class Upstream:
    """MCP-клиент моста oc-mcp. Используется как асинхронный контекстный менеджер."""

    def __init__(self, cmd: list[str], env: dict | None = None):
        self.cmd = list(cmd)
        self.env = env
        self.session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> "Upstream":
        self._stack = AsyncExitStack()
        params = StdioServerParameters(command=self.cmd[0], args=self.cmd[1:], env=self.env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()

    async def call(self, name: str, args: dict) -> tuple[bool, str, str | None]:
        try:
            result = await self.session.call_tool(name, args)
        except MCPError as e:
            if e.code == INVALID_PARAMS:
                return False, f"bad argument: {e.message}", "BLOCKED"
            return False, e.message, None
        text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
        code = (result.structured_content or {}).get("error_code") if result.is_error else None
        return not result.is_error, text, code

    async def list_tools(self) -> list[dict]:
        """Tools oc-mcp: name, description, inputSchema."""
        tools = (await self.session.list_tools()).tools
        return [{"name": t.name, "description": t.description or "", "inputSchema": t.input_schema} for t in tools]
