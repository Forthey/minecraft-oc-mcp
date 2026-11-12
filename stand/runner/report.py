"""Отчёты: report.md одного прогона и summary.md по всем прогонам."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

DIFF_LIMIT = 20


def write(run_dir: Path, results: dict) -> None:
    """Пишет results.json и report.md в папку прогона."""
    (run_dir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "report.md").write_text(render_report(results), encoding="utf-8")


def _fmt(v, digits: int = 1) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _judge_section(judge: dict | None) -> list[str]:
    if not judge:
        return []
    out = ["## Судья", "", f"Режим {judge.get('mode')}, точность {_fmt(judge.get('accuracy'), 3)}, "
           f"лишних изменений {judge.get('extra_count')}.", ""]
    details = judge.get("details") or {}
    if judge.get("mode") == "relational":
        out += ["| Структура | Найдена | Начало | Поворот | Точность | Якорь | Толкование | Сдвиг |",
                "|---|---|---|---|---|---|---|---|"]
        for sid, st in (details.get("structures") or {}).items():
            out.append(f"| {sid} | {st.get('found')} | {st.get('origin')} | {st.get('rotation')} | "
                       f"{_fmt(st.get('accuracy'), 3)} | {_fmt(st.get('anchor_ok'))} | "
                       f"{_fmt(st.get('interpretation'))} | {st.get('offset')} |")
        out.append("")
    for key, title in (("missing", "Пропущены"), ("wrong", "Чужие блоки"), ("extra", "Лишние изменения")):
        items = details.get(key) or []
        if not items:
            continue
        out.append(f"**{title}** ({len(items)}):")
        out.append("")
        for it in items[:DIFF_LIMIT]:
            rest = ", ".join(f"{k} {v}" for k, v in it.items() if k != "pos")
            out.append(f"- {it.get('pos')}" + (f": {rest}" if rest else ""))
        if len(items) > DIFF_LIMIT:
            out.append(f"- и ещё {len(items) - DIFF_LIMIT}")
        out.append("")
    if judge.get("snapshot_mismatch"):
        out += [f"Снимок разошёлся с testforblock: {judge['snapshot_mismatch']}", ""]
    return out


def _memory(m: dict | None) -> str:
    if not m:
        return "-"
    if not m.get("used"):
        return "не открывалась"
    return (f"сессий {m['agent_sessions']}, мест +{m['pois_added']}, уроков +{m['episodes_added']}, "
            f"фактов +{m['facts_added']}, склад {'запомнен' if m['warehouse_remembered'] else 'не запомнен'}")


def render_report(r: dict) -> str:
    """Markdown-отчёт одного прогона."""
    usage = r.get("usage") or {}
    lines = [
        f"# {r.get('run_id', 'run')}: {r.get('status')}",
        "",
        f"Сценарий {r.get('scenario')}, агент {r.get('agent')}, MCP {r.get('robot_mcp', '-')}, "
        f"профиль {r.get('profile', '-')}.",
        "",
        "| Метрика | Значение |",
        "|---|---|",
        f"| Время, с | {_fmt(r.get('duration_s'))} |",
        f"| Вызовов tools | {_fmt(r.get('calls_total'))} |",
        f"| По группам | {r.get('calls_by_group') or '-'} |",
        f"| Ошибки по кодам | {r.get('errors_by_code') or '-'} |",
        f"| Агент заявил успех | {_fmt(r.get('claimed_success'))} |",
        f"| Ложный успех | {_fmt(r.get('false_success'))} |",
        f"| Код выхода агента | {_fmt(r.get('exit_code'))} |",
        f"| Токены вход/кэш/выход | {_fmt(usage.get('input_tokens'))} / {_fmt(usage.get('cached_input_tokens'))} / "
        f"{_fmt(usage.get('output_tokens'))} |",
        f"| Стоимость, $ | {_fmt(usage.get('cost_usd'), 4)} |",
        f"| Точность spec.json | {(r.get('spec_accuracy') or {}).get('accuracy', '-')} |",
        f"| Память | {_memory(r.get('memory'))} |",
        "",
    ]
    if usage.get("agent_error"):
        lines += ["## Ошибка агента", "",
                  "Прогон оборван ошибкой провайдера или CLI агента и не отражает поведение скиллов.", "",
                  "```", str(usage["agent_error"])[:1000], "```", ""]
    lines += _judge_section(r.get("judge"))
    violations = r.get("violations") or []
    lines += ["## Нарушения правил", ""]
    if violations:
        for v in violations:
            where = f" (action_log.jsonl:{v['log_line']})" if v.get("log_line") else ""
            lines.append(f"- **{v['rule']}**{where}: {v.get('detail', '')}")
    else:
        lines.append("Нет.")
    lines.append("")
    if r.get("faults"):
        lines += ["## Внедрённые сбои", ""]
        for f in r["faults"]:
            lines.append(f"- action_log.jsonl:{f['log_line']} {f['tool']} {f['error_code']}, "
                         f"следующий вызов: {f['next_tool']}")
        lines.append("")
    if usage.get("final_text"):
        lines += ["## Финальный ответ агента", "", "```", str(usage["final_text"])[:2000], "```", ""]
    return "\n".join(lines)


def _median(values: list) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return statistics.median(vals) if vals else None


def build_summary(runs_dir: Path) -> str:
    """Таблица сценарий на агент по всем results.json в runs_dir."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for path in sorted(runs_dir.glob("*/results.json")):
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        groups.setdefault((r.get("scenario", "?"), r.get("agent", "?")), []).append(r)
    lines = [
        "# Сводка прогонов",
        "",
        "| Сценарий | Агент | Прогонов | PASS | Медиана времени, с | Медиана вызовов | Медиана стоимости, $ "
        "| Ложный успех | Нарушения | Пропущено |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (scenario, agent), rs in sorted(groups.items()):
        done = [r for r in rs if r.get("status") != "SKIPPED"]
        passed = sum(1 for r in done if r.get("status") == "PASS")
        lines.append(
            f"| {scenario} | {agent} | {len(done)} | {passed}/{len(done)} | "
            f"{_fmt(_median([r.get('duration_s') for r in done]))} | "
            f"{_fmt(_median([r.get('calls_total') for r in done]))} | "
            f"{_fmt(_median([(r.get('usage') or {}).get('cost_usd') for r in done]), 4)} | "
            f"{sum(1 for r in done if r.get('false_success'))} | "
            f"{sum(len(r.get('violations') or []) for r in done)} | "
            f"{len(rs) - len(done)} |"
        )
    statuses: dict[str, int] = {}
    for rs in groups.values():
        for r in rs:
            statuses[r.get("status", "?")] = statuses.get(r.get("status", "?"), 0) + 1
    lines += ["", "Статусы: " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())), ""]
    return "\n".join(lines)


def write_summary(runs_dir: Path) -> Path:
    path = runs_dir / "summary.md"
    runs_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(build_summary(runs_dir), encoding="utf-8")
    return path
