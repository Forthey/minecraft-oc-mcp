"""Агент-скрипт: выполняет готовый список вызовов tools вместо LLM.

python -m stand.runner.script_agent --mcp-config <mcp.json> --script <script.json>

Нужен, чтобы проверить стенд целиком без модели: runner, fake-MCP, мир, судью и
метрики. Сервер MCP берётся из того же mcp.json, что получает Claude Code, поэтому
цепочка та же. Скрипт это JSON-список [{"tool": ..., "args": {...}}]. Шаг с полем
"expect": "<код ошибки>" обязан вернуть эту ошибку, тогда скрипт идёт дальше. Так
записываются сценарии с отказами вроде NO_PATH и CONNECTION_LOST.

Агент пишет журнал .oc-tasks/script/journal.md в формате оркестратора: строку
постройки, строку проверки (если в скрипте был verify_blocks) и финал. Финал DONE,
если все вызовы ok и verify_blocks не нашёл расхождений, иначе FAILED. Код выхода
0 или 1 соответственно.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from stand.conformance.checks import parse_envelope

SERVER = "robot"
STAGE = "script"


def _line(phase: str, stage: str, status: str, done: int, total: int, calls: int) -> str:
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return (f"[{ts}] phase={phase} stage={stage} role=orchestrator status={status} "
            f"delta={done}/{total} calls={calls} budget=-")


def _problem(tool: str, env: dict, expect: str | None = None) -> str | None:
    """Почему вызов считается неудачным, или None. expect это код ошибки, который шаг должен вернуть."""
    if expect is not None:
        got = "ok" if env["ok"] else env.get("error_code")
        return None if got == expect else f"expected {expect}, got {got}"
    if not env["ok"]:
        return f"{env.get('error_code')}: {env['message']}"
    if tool == "verify_blocks":
        data = env["data"]
        if data.get("missing") or data.get("wrong"):
            return f"verify_blocks found missing {data.get('missing')} wrong {data.get('wrong')}"
    return None


async def run_script(spec: dict, calls: list[dict], journal: Path) -> bool:
    """Выполняет вызовы по порядку, пишет журнал. True, если всё прошло."""
    params = StdioServerParameters(
        command=spec["command"],
        args=list(spec.get("args", [])),
        env={**os.environ, **spec.get("env", {})},
    )
    journal.parent.mkdir(parents=True, exist_ok=True)
    done = 0
    verified = False
    failure = None
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for i, call in enumerate(calls, 1):
                env = parse_envelope(await session.call_tool(call["tool"], call.get("args") or {}))
                problem = _problem(call["tool"], env, call.get("expect"))
                print(f"{i:3} {call['tool']:16} {'FAILED' if problem else 'ok'}" + (f"  {problem}" if problem else ""))
                if problem:
                    failure = problem
                    break
                done += 1
                verified = verified or call["tool"] == "verify_blocks"
    # Журнал как у оркестратора: постройка одним этапом, проверка, если она была, и финал.
    calls_made = done + (failure is not None)
    status = "DONE" if failure is None else "FAILED"
    with open(journal, "a", encoding="utf-8") as j:
        j.write(_line("build", STAGE, status, done, len(calls), calls_made) + "\n")
        if verified:
            j.write(_line("verify", STAGE, status, done, len(calls), 1) + "\n")
        j.write(_line("final", "-", status, done, len(calls), calls_made) + "\n")
    return failure is None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stand.runner.script_agent")
    parser.add_argument("--mcp-config", required=True, type=Path)
    parser.add_argument("--script", required=True, type=Path)
    args = parser.parse_args(argv)
    spec = json.loads(args.mcp_config.read_text(encoding="utf-8"))["mcpServers"][SERVER]
    calls = json.loads(args.script.read_text(encoding="utf-8"))
    ok = anyio.run(run_script, spec, calls, Path(".oc-tasks") / "script" / "journal.md")
    print("script finished: " + ("all calls succeeded" if ok else "stopped on a failed call"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
