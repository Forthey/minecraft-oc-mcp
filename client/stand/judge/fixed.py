"""Судья режима fixed: каждый ожидаемый блок в заданной точке."""

from __future__ import annotations

from dataclasses import dataclass

from stand.judge.common import block_json, extra_cells
from stand.knowledge import Knowledge
from stand.world.blocks import AIR, Block, Pos
from stand.world.snapshot import Snapshot


@dataclass
class FixedResult:
    """Итог сверки: верные, пропущенные, чужие и лишние блоки."""

    correct: int
    total: int
    missing: list[Pos]
    wrong: list[tuple[Pos, Block, Block]]
    extra: list[tuple[Pos, Block]]
    accuracy: float
    passed: bool

    def to_dict(self) -> dict:
        return {
            "correct": self.correct,
            "total": self.total,
            "accuracy": self.accuracy,
            "missing": [{"pos": list(p)} for p in self.missing],
            "wrong": [
                {"pos": list(p), "expected": block_json(e), "actual": block_json(a)}
                for p, e, a in self.wrong
            ],
            "extra": [{"pos": list(p), "actual": block_json(a)} for p, a in self.extra],
        }


def judge_fixed(
    snap: Snapshot,
    expected: dict[Pos, Block],
    scene: dict[Pos, Block],
    removable: set[Pos],
    scoring: dict,
    k: Knowledge,
) -> FixedResult:
    """Сверяет снимок с ожидаемыми блоками.

    Пропущен: на месте воздух. Чужой: стоит другой блок. Лишние изменения ищет
    extra_cells. PASS при accuracy >= pass_accuracy и числе лишних <= max_extra.
    """
    correct = 0
    missing: list[Pos] = []
    wrong: list[tuple[Pos, Block, Block]] = []
    for p in sorted(expected):
        want = expected[p]
        actual = snap.get(p)
        if k.block_matches(want, actual):
            correct += 1
        elif actual == AIR:
            missing.append(p)
        else:
            wrong.append((p, want, actual))
    total = len(expected)
    accuracy = correct / total if total else 1.0
    extra = extra_cells(snap, scene, removable, set(expected), k)
    passed = accuracy >= scoring["pass_accuracy"] and len(extra) <= scoring["max_extra"]
    return FixedResult(correct, total, missing, wrong, extra, accuracy, passed)
