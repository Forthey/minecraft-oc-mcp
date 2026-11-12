"""Журнал вызовов tools: по строке JSONL на вызов. Из него runner считает метрики."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# Поля data, которые сохраняются в журнал: по ним считаются метрики правил
# (например, dug для ломания рядом с постройкой). Остальное не нужно и раздувает файл.
KEPT_DATA = ("pos", "dug", "robot")


class ActionLog:
    """Журнал в памяти и, если задан путь, в файле JSONL (дописывается сразу)."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.entries: list[dict] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, tool: str, args: dict, envelope: dict, duration_ms: float, fault: bool) -> dict:
        data = envelope.get("data") or {}
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "tool": tool,
            "args": args,
            "ok": bool(envelope.get("ok")),
            "error_code": envelope.get("error_code"),
            "duration_ms": round(duration_ms, 2),
            "fault": fault,
            "data": {k: data[k] for k in KEPT_DATA if k in data},
        }
        self.entries.append(entry)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry
