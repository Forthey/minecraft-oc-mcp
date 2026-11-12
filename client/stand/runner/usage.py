"""Разбор вывода агентов: токены, стоимость, финальный ответ, вызовы tools.

Форматы проверены на claude 2.1.322 (stream-json), codex-cli 0.167.0 (exec --json)
и opencode 2.1.0 (run --format json). Битые строки и не UTF-8 пропускаются.
"""

from __future__ import annotations

import json
from pathlib import Path

TAIL_CHARS = 2000


def _events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_bytes().decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def _empty() -> dict:
    return {"input_tokens": None, "output_tokens": None, "cached_input_tokens": None,
            "cost_usd": None, "final_text": None, "num_turns": None, "agent_error": None}


def _agent_error(kind: str, events: list[dict]) -> str | None:
    """Последняя ошибка провайдера или CLI агента из вывода. None, если ошибок не было.

    Такая ошибка (квота, перегрузка API) обрывает прогон, и он не отражает
    поведение скиллов, даже если судья дал PASS.
    """
    for e in reversed(events):
        if kind == "claude_stream_json" and e.get("type") == "result" and e.get("is_error"):
            return f"{e.get('subtype', 'error')}: {e.get('result', '')}".strip()
        if kind == "codex_json" and e.get("type") in ("turn.failed", "error"):
            err = e.get("error") if isinstance(e.get("error"), dict) else {}
            return str(err.get("message") or e.get("message") or e.get("type"))
        if kind == "opencode_json" and e.get("type") == "error":
            err = e.get("error") if isinstance(e.get("error"), dict) else {}
            message = err.get("message") or (err.get("data") or {}).get("message") or ""
            return f"{err.get('type', 'error')}: {message}".strip()
    return None


def parse_usage(kind: str, transcript: Path) -> dict:
    """Токены, стоимость и финальный текст. Неизвестное значение None."""
    u = _empty()
    events = _events(transcript)
    u["agent_error"] = _agent_error(kind, events)
    if kind == "claude_stream_json":
        result = next((e for e in reversed(events) if e.get("type") == "result"), None)
        if result:
            usage = result.get("usage") or {}
            u.update(
                # Запись в кэш тоже некэшированный вход, иначе вход выглядит как десятки токенов.
                input_tokens=(None if usage.get("input_tokens") is None
                              else usage["input_tokens"] + (usage.get("cache_creation_input_tokens") or 0)),
                output_tokens=usage.get("output_tokens"),
                cached_input_tokens=usage.get("cache_read_input_tokens"),
                cost_usd=result.get("total_cost_usd"),
                final_text=result.get("result"),
                num_turns=result.get("num_turns"),
            )
        return u
    if kind == "codex_json":
        turns = [e["usage"] for e in events if e.get("type") == "turn.completed" and isinstance(e.get("usage"), dict)]
        if turns:
            u["input_tokens"] = sum(t.get("input_tokens", 0) for t in turns)
            u["output_tokens"] = sum(t.get("output_tokens", 0) for t in turns)
            u["cached_input_tokens"] = sum(t.get("cached_input_tokens", 0) for t in turns)
            u["num_turns"] = len(turns)
        messages = [e["item"].get("text") for e in events
                    if e.get("type") == "item.completed" and (e.get("item") or {}).get("type") == "agent_message"]
        u["final_text"] = messages[-1] if messages else None
        return u
    if kind == "opencode_json":
        # Токены и стоимость opencode пишет в каждом step_finish, итог это сумма по шагам.
        steps = [e["part"] for e in events
                 if (e.get("part") or {}).get("type") == "step-finish" and isinstance(e["part"].get("tokens"), dict)]
        if steps:
            u["input_tokens"] = sum(s["tokens"].get("input", 0) for s in steps)
            u["output_tokens"] = sum(s["tokens"].get("output", 0) for s in steps)
            u["cached_input_tokens"] = sum((s["tokens"].get("cache") or {}).get("read", 0) for s in steps)
            u["cost_usd"] = sum(s.get("cost") or 0 for s in steps)
            u["num_turns"] = len(steps)
        texts = [(e.get("part") or {}).get("text") for e in events if (e.get("part") or {}).get("type") == "text"]
        u["final_text"] = texts[-1] if texts else None
        return u
    if transcript.exists():
        u["final_text"] = transcript.read_bytes().decode("utf-8", errors="replace")[-TAIL_CHARS:].strip() or None
    return u


def tool_inputs(kind: str, transcript: Path) -> list[str]:
    """Аргументы всех вызовов tools агентом строками JSON. Для неизвестного формата весь вывод."""
    events = _events(transcript)
    if kind == "claude_stream_json":
        out = []
        for e in events:
            if e.get("type") != "assistant":
                continue
            for part in (e.get("message") or {}).get("content") or []:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    out.append(json.dumps({"name": part.get("name"), "input": part.get("input")}, ensure_ascii=False))
        return out
    if kind == "codex_json":
        return [json.dumps(e["item"], ensure_ascii=False) for e in events
                if e.get("type") in ("item.started", "item.completed")
                and (e.get("item") or {}).get("type") not in (None, "agent_message", "reasoning")]
    if kind == "opencode_json":
        return [json.dumps(e["part"], ensure_ascii=False) for e in events
                if (e.get("part") or {}).get("type") == "tool"]
    if not transcript.exists():
        return []
    return [transcript.read_bytes().decode("utf-8", errors="replace")]


def robot_calls(kind: str, transcript: Path, server: str = "robot") -> list[dict]:
    """Вызовы tools сервера робота по выводу агента, без результатов.

    Запасной action log для реального MCP без get_action_log: ok и error_code
    неизвестны, поэтому метрики ошибок по такому журналу не считаются.
    """
    out = []
    prefix = f"mcp__{server}__"
    for e in _events(transcript):
        if kind == "claude_stream_json" and e.get("type") == "assistant":
            for part in (e.get("message") or {}).get("content") or []:
                name = part.get("name", "") if isinstance(part, dict) else ""
                if part.get("type") == "tool_use" and name.startswith(prefix):
                    out.append({"tool": name[len(prefix):], "args": part.get("input") or {}, "ok": None,
                                "error_code": None, "fault": False, "data": {}})
        if kind == "codex_json" and e.get("type") == "item.completed":
            item = e.get("item") or {}
            if item.get("type") == "mcp_tool_call" and item.get("server") == server:
                out.append({"tool": item.get("tool"), "args": item.get("arguments") or {}, "ok": None,
                            "error_code": None, "fault": False, "data": {}})
    return out
