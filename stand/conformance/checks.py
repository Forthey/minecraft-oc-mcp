"""Набор контрактных проверок MCP-сервера робота.

Проверки работают через любую сессию MCP с методами list_tools и call_tool, так что
одинаково прогоняются против fake-MCP и против реального сервера команды. Сцена
описана в scene.yaml и scenario.yaml рядом с этим файлом.

Проверяется только то, что агент считает гарантированным: набор tools, форма
конверта, коды ошибок в простых ситуациях. Корректность pathfinding или зрения
сюда не входит.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import yaml

from stand.config import Config
from agent.tools.validate_skills import contract_error_codes, contract_tools

CONFORMANCE_DIR = Path(__file__).resolve().parent
ROOT = CONFORMANCE_DIR.parents[1]
CONTRACT = ROOT / "agent" / "skills" / "references" / "tool-contract.md"


@dataclass
class CheckResult:
    """Итог одной проверки."""

    name: str
    ok: bool
    detail: str


class EnvelopeError(ValueError):
    """Ответ tool не соответствует конверту контракта."""


def load_scene(path: Path = CONFORMANCE_DIR / "scene.yaml") -> dict:
    """Параметры сцены. scenario_path уже абсолютный."""
    scene = yaml.safe_load(path.read_text(encoding="utf-8"))
    scene["scenario_path"] = (path.parent / scene["scenario"]).resolve()
    return scene


def parse_envelope(result) -> dict:
    """Достаёт конверт из ответа call_tool и проверяет его форму."""
    texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    if not texts:
        raise EnvelopeError("tool returned no text content")
    try:
        env = json.loads(texts[0])
    except json.JSONDecodeError as e:
        raise EnvelopeError(f"text content is not JSON: {e}") from e
    if not isinstance(env, dict):
        raise EnvelopeError("envelope is not an object")
    if not isinstance(env.get("ok"), bool):
        raise EnvelopeError("field ok is missing or not boolean")
    if not isinstance(env.get("message"), str):
        raise EnvelopeError("field message is missing or not a string")
    if not isinstance(env.get("data"), dict):
        raise EnvelopeError("field data is missing or not an object")
    if not env["ok"] and not isinstance(env.get("error_code"), str):
        raise EnvelopeError("ok is false but error_code is missing")
    return env


async def _call(session, name: str, args: dict) -> dict:
    return parse_envelope(await session.call_tool(name, args))


def _expect_code(env: dict, code: str, codes: set[str]) -> tuple[bool, str]:
    got = env.get("error_code") if not env["ok"] else None
    if got is not None and got not in codes:
        return False, f"error_code {got} is not in the contract, expected {code}"
    if got != code:
        return False, f"expected {code}, got {'ok' if env['ok'] else got}: {env['message']}"
    return True, f"{code}: {env['message']}"


async def check_tools(session, scene: dict, codes: set[str]) -> CheckResult:
    listed = {t.name for t in (await session.list_tools()).tools}
    expected = contract_tools(CONTRACT)
    missing = sorted(expected - listed)
    extra = sorted(listed - expected)
    detail = f"{len(listed & expected)}/{len(expected)} contract tools"
    if missing:
        detail += f", missing: {', '.join(missing)}"
    if extra:
        detail += f", extra (allowed): {', '.join(extra)}"
    return CheckResult("tools_match_contract", not missing, detail)


async def check_envelope(session, scene: dict, codes: set[str]) -> CheckResult:
    env = await _call(session, "get_status", {})
    data = env["data"]
    pos = data.get("pos")
    if not env["ok"]:
        return CheckResult("envelope_shape", False, f"get_status failed: {env.get('error_code')}")
    if not (isinstance(pos, list) and len(pos) == 3 and all(isinstance(v, int) for v in pos)):
        return CheckResult("envelope_shape", False, f"get_status data.pos must be [x, y, z], got {pos!r}")
    if data.get("facing") not in ("north", "south", "east", "west"):
        return CheckResult("envelope_shape", False, f"get_status data.facing is {data.get('facing')!r}")
    return CheckResult("envelope_shape", True, f"get_status pos {pos}, facing {data['facing']}")


async def check_blocked_on_occupied(session, scene: dict, codes: set[str]) -> CheckResult:
    # Сначала берём предмет со склада, иначе сервер может законно ответить NO_ITEM.
    side = scene["warehouse_side"]
    took = await _call(session, "storage_take", {"side": side, "slot": 1, "count": 1})
    if not took["ok"]:
        return CheckResult("blocked_on_occupied", False,
                           f"setup failed: storage_take slot 1 returned {took.get('error_code')}")
    slot = None
    inv = await _call(session, "inventory_scan", {})
    for entry in inv["data"].get("slots", []):
        slot = entry.get("slot")
        break
    if slot is None:
        return CheckResult("blocked_on_occupied", False, "setup failed: inventory_scan shows no slots after storage_take")
    env = await _call(session, "place", {"side": scene["occupied_side"], "slot": slot})
    return CheckResult("blocked_on_occupied", *_expect_code(env, "BLOCKED", codes))


async def check_no_item(session, scene: dict, codes: set[str]) -> CheckResult:
    env = await _call(session, "storage_take", {"side": scene["warehouse_side"], "slot": scene["empty_slot"], "count": 1})
    return CheckResult("no_item_on_empty_slot", *_expect_code(env, "NO_ITEM", codes))


async def check_out_of_range(session, scene: dict, codes: set[str]) -> CheckResult:
    x, y, z = scene["far_point"]
    env = await _call(session, "move_to", {"x": x, "y": y, "z": z, "policy": "avoid"})
    return CheckResult("out_of_range", *_expect_code(env, "OUT_OF_RANGE", codes))


async def check_unknown_item(session, scene: dict, codes: set[str]) -> CheckResult:
    # Существует ли предмет, знает только NEI. Без игрока онлайн NEI отвечает NO_PROVIDER,
    # это не ошибка сервера: доступность NEI проверяет nei_available.
    env = await _call(session, "nei_recipes", {"item": scene["unknown_item"]})
    if not env["ok"] and env.get("error_code") == "NO_PROVIDER":
        return CheckResult("unknown_item", True, "NO_PROVIDER: item check skipped, NEI unavailable")
    return CheckResult("unknown_item", *_expect_code(env, "UNKNOWN_ITEM", codes))


async def check_nei_available(session, scene: dict, codes: set[str]) -> CheckResult:
    env = await _call(session, "nei_find", {"text": scene["nei_item"]})
    if env["ok"]:
        return CheckResult("nei_available", True, f"nei_find returned {len(env['data'].get('items', []))} items")
    return CheckResult("nei_available", *_expect_code(env, "NO_PROVIDER", codes))


CHECKS = [
    ("tools_match_contract", check_tools),
    ("envelope_shape", check_envelope),
    ("blocked_on_occupied", check_blocked_on_occupied),
    ("no_item_on_empty_slot", check_no_item),
    ("out_of_range", check_out_of_range),
    ("unknown_item", check_unknown_item),
    ("nei_available", check_nei_available),
]


async def run_checks(session, scene: dict) -> list[CheckResult]:
    """Прогоняет все проверки по порядку. Ошибка одной не останавливает остальные."""
    codes = contract_error_codes(CONTRACT)
    results = []
    for name, check in CHECKS:
        try:
            results.append(await check(session, scene, codes))
        except EnvelopeError as e:
            results.append(CheckResult(name, False, f"bad envelope: {e}"))
        except Exception as e:  # noqa: BLE001 - проверка должна сообщить о любой ошибке сервера
            results.append(CheckResult(name, False, f"{type(e).__name__}: {e}"))
    return results


@asynccontextmanager
async def connect(target: str, cfg: Config, scene: dict | None = None):
    """Открывает сессию MCP.

    fake: запускает fake-MCP стенда по stdio с миром в памяти на сцене conformance.
    real: команда cfg.real["command"] (stdio) или адрес cfg.real["url"] (streamable HTTP).
    """
    from mcp.client.session import ClientSession

    scene = scene or load_scene()
    if target == "fake":
        from mcp.client.stdio import StdioServerParameters, stdio_client

        env = dict(os.environ, PYTHONPATH=str(ROOT))
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "stand.fake_mcp", "--scenario", str(scene["scenario_path"]), "--world", "memory"],
            cwd=str(ROOT),
            env=env,
        )
        transport = stdio_client(params)
    elif cfg.real.get("command"):
        from mcp.client.stdio import StdioServerParameters, stdio_client

        import tempfile

        from stand.config import render_real_command

        log = Path(tempfile.gettempdir()) / "oc-conformance-action_log.jsonl"
        cmd = render_real_command(cfg, scene["scenario_path"], log)
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        transport = stdio_client(StdioServerParameters(command=cmd[0], args=cmd[1:], env=env))
    elif cfg.real.get("url"):
        from mcp.client.streamable_http import streamable_http_client

        transport = streamable_http_client(cfg.real["url"])
    else:
        raise ValueError("set real.command or real.url in stand/config.yaml or stand/config.local.yaml")
    async with transport as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session
