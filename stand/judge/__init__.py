"""Судья: сверяет снимок мира с ожиданием сценария. От MCP и отчёта агента не зависит."""

from __future__ import annotations

from stand.judge.fixed import judge_fixed
from stand.knowledge import Knowledge
from stand.scenario import Scenario
from stand.world.snapshot import Snapshot


def judge(snap: Snapshot, scenario: Scenario, k: Knowledge) -> dict:
    """Вердикт по сценарию в сериализуемом виде.

    Ключи: mode, passed, accuracy, extra_count и details с подробностями режима.
    """
    scene = scenario.scene_blocks()
    mode = scenario.expected["mode"]
    if mode == "fixed":
        r = judge_fixed(snap, scenario.fixed_expected(), scene, scenario.removable, scenario.scoring, k)
        return {
            "mode": mode,
            "passed": r.passed,
            "accuracy": r.accuracy,
            "extra_count": len(r.extra),
            "details": r.to_dict(),
        }
    from stand.judge.relational import judge_relational

    details = judge_relational(snap, scenario, k)
    return {
        "mode": mode,
        "passed": details["passed"],
        "accuracy": details["accuracy"],
        "extra_count": len(details["extra"]),
        "details": details,
    }
