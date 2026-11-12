"""Метрики прогона: статус, вызовы, ошибки, реакция на сбои, нарушения правил скиллов.

Источники: action_log.jsonl (вызовы tools), journal/ (копия .oc-tasks агента),
вывод агента (usage), вердикт судьи. Любой источник может отсутствовать, тогда
соответствующие метрики пустые, а прогон всё равно получает результаты.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from stand.fake_mcp.dispatch import TOOL_SPECS
from stand.knowledge import Knowledge
from stand.runner.agents import AgentRun
from stand.runner.usage import tool_inputs
from stand.scenario import Scenario
from stand.world.blocks import parse_block
from tools.validate_skills import JOURNAL_LINE_RE

FIELD_RE = re.compile(r"(\w+)=(\S+)")
BUDGET_RE = re.compile(r"^([\w-]+):(\d+)/(\d+)$")
LEAK_PATTERNS = ("stand/scenarios", "stand/knowledge", "mcp_scenario.yaml", "scenario-schema.json")
NEIGHBOURS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def read_action_log(path: Path) -> list[dict]:
    """Записи action log. Битые строки пропускаются."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_journal(journal_dir: Path) -> list[dict]:
    """Статус-строки journal.md всех задач агента, поля разобраны в словарь."""
    lines = []
    for path in sorted(journal_dir.glob("**/journal.md")):
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = raw.strip()
            if JOURNAL_LINE_RE.match(raw):
                lines.append(dict(FIELD_RE.findall(raw)))
    return lines


def _repeated_calls(log: list[dict]) -> list[dict]:
    # Правило 1 из error-handling.md: тот же tool с теми же аргументами и той же
    # ошибкой не вызывается в третий раз. Подряд это быть не обязано.
    seen: dict[str, int] = {}
    out = []
    for i, e in enumerate(log, 1):
        # ok None значит результат неизвестен (журнал восстановлен из вывода агента).
        if e.get("ok") is not False:
            continue
        key = json.dumps([e.get("tool"), e.get("args"), e.get("error_code")], sort_keys=True)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 3:
            out.append({"rule": "repeated_call", "log_line": i,
                        "detail": f"{e.get('tool')} {json.dumps(e.get('args'))} failed with {e.get('error_code')} 3 times"})
    return out


def _dig_near_structure(log: list[dict]) -> list[dict]:
    placed: set[tuple] = set()
    out = []
    for i, e in enumerate(log, 1):
        data = e.get("data") or {}
        if e.get("ok") and e.get("tool") in ("place", "place_at") and data.get("pos"):
            placed.add(tuple(data["pos"]))
        dug = [tuple(p) for p in data.get("dug") or []]
        if e.get("ok") and e.get("tool") == "swing" and data.get("pos"):
            dug.append(tuple(data["pos"]))
        near = [p for p in dug if any((p[0] + d[0], p[1] + d[1], p[2] + d[2]) in placed for d in NEIGHBOURS)]
        if near:
            out.append({"rule": "dig_near_structure", "log_line": i,
                        "detail": f"{e.get('tool')} broke {[list(p) for p in near]} next to placed blocks"})
        placed -= set(dug)
    return out


def _journal_rules(journal: list[dict], harness: dict) -> list[dict]:
    out = []
    per_stage = (harness.get("budgets") or {}).get("robot_calls_per_stage")
    for i, line in enumerate(journal):
        if line.get("phase") == "build" and line.get("status") == "DONE":
            stage = line.get("stage")
            later = journal[i + 1:]
            if not any(l.get("phase") == "verify" and l.get("stage") == stage for l in later):
                out.append({"rule": "done_without_verify", "log_line": None,
                            "detail": f"stage {stage} is DONE without a verify line after it"})
        m = BUDGET_RE.match(line.get("budget", ""))
        if m and int(m.group(2)) > int(m.group(3)):
            out.append({"rule": "budget_exceeded", "log_line": None,
                        "detail": f"{line.get('phase')} {line.get('stage')}: {line['budget']}"})
        if per_stage and line.get("phase") == "build" and int(line.get("calls", 0)) > per_stage:
            out.append({"rule": "budget_exceeded", "log_line": None,
                        "detail": f"build {line.get('stage')}: calls={line['calls']} > {per_stage}"})
    return out


def _answer_leak(kind: str, transcript: Path) -> list[dict]:
    out = []
    for text in tool_inputs(kind, transcript):
        norm = text.replace("\\\\", "/").replace("\\", "/")
        hits = [p for p in LEAK_PATTERNS if p in norm]
        if hits:
            out.append({"rule": "answer_leak", "log_line": None,
                        "detail": f"agent tool call touched {', '.join(hits)}: {text[:200]}"})
    return out


def _spec_accuracy(journal_dir: Path, s: Scenario, k: Knowledge) -> dict | None:
    """Насколько spec.json агента совпадает с ожиданием (только режим fixed)."""
    expected = s.fixed_expected()
    specs = sorted(journal_dir.glob("**/spec.json"), key=lambda p: p.stat().st_mtime)
    if not expected or not specs:
        return None
    try:
        spec = json.loads(specs[-1].read_text(encoding="utf-8"))
        ox, oy, oz = spec["origin"]
        planned = {}
        for stage in spec["stages"]:
            for b in stage.get("blocks", []):
                x, y, z = b["pos"]
                planned[(ox + x, oy + y, oz + z)] = k.block_for(b["item"]) or parse_block(b["item"])
    except (KeyError, ValueError, TypeError):
        return None
    hits = sum(1 for p, want in expected.items() if p in planned and k.block_matches(want, planned[p]))
    return {"accuracy": hits / len(expected), "extra": len(set(planned) - set(expected))}


def collect(
    run_dir: Path,
    s: Scenario,
    k: Knowledge,
    judge_result: dict,
    agent_run: AgentRun,
    usage: dict,
    harness: dict,
    usage_kind: str,
) -> dict:
    """Все метрики прогона одним словарём."""
    log = read_action_log(run_dir / "action_log.jsonl")
    journal = read_journal(run_dir / "journal")
    claimed = any(l.get("phase") == "final" and l.get("status") == "DONE" for l in journal)
    final_text = (usage.get("final_text") or "").strip()

    if agent_run.timed_out:
        status = "TIMEOUT"
    elif final_text.endswith("?") and not claimed and not judge_result["passed"]:
        status = "ASKED"
    elif judge_result["passed"]:
        status = "PASS"
    elif agent_run.exit_code not in (0, None):
        status = "CRASH"
    else:
        status = "FAIL"

    by_group: dict[str, int] = {}
    errors: dict[str, int] = {}
    faults = []
    for i, e in enumerate(log, 1):
        spec = TOOL_SPECS.get(e.get("tool"))
        group = spec.group if spec else "other"
        by_group[group] = by_group.get(group, 0) + 1
        if not e.get("ok") and e.get("error_code"):
            errors[e["error_code"]] = errors.get(e["error_code"], 0) + 1
        if e.get("fault"):
            nxt = log[i]["tool"] if i < len(log) else None
            faults.append({"log_line": i, "tool": e.get("tool"), "error_code": e.get("error_code"), "next_tool": nxt})

    violations = (
        _repeated_calls(log)
        + _dig_near_structure(log)
        + _journal_rules(journal, harness)
        + _answer_leak(usage_kind, run_dir / "transcript.jsonl")
    )
    return {
        "status": status,
        "claimed_success": claimed,
        "false_success": claimed and not judge_result["passed"],
        "judge": judge_result,
        "duration_s": round(agent_run.duration_s, 1),
        "exit_code": agent_run.exit_code,
        "calls_total": len(log),
        "calls_by_group": by_group,
        "errors_by_code": errors,
        "faults": faults,
        "violations": violations,
        "usage": usage,
        "spec_accuracy": _spec_accuracy(run_dir / "journal", s, k),
        "journal_lines": len(journal),
    }
