"""Конверт ответа tool: {ok, error_code?, message, data}."""

from __future__ import annotations


def ok(message: str, data: dict | None = None) -> dict:
    """Успешный ответ."""
    return {"ok": True, "message": message, "data": data or {}}


def err(code: str, message: str, data: dict | None = None) -> dict:
    """Ответ с кодом ошибки из контракта."""
    return {"ok": False, "error_code": code, "message": message, "data": data or {}}
