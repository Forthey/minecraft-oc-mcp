"""Общее для режимов судьи: поиск лишних изменений мира."""

from __future__ import annotations

from stand.knowledge import Knowledge
from stand.world.blocks import AIR, Block, Pos, baseline_block, format_block
from stand.world.snapshot import Snapshot

# Блоки самого робота OpenComputers в режиме real. Робот стоит в регионе как блок, а при
# движении на миг оставляет afterimage. Это не постройка агента, и судья их не считает.
ROBOT_BLOCKS = {"OpenComputers:robot", "OpenComputers:robotAfterimage"}


def extra_cells(
    snap: Snapshot,
    scene: dict[Pos, Block],
    removable: set[Pos],
    exclude: set[Pos],
    k: Knowledge,
) -> list[tuple[Pos, Block]]:
    """Клетки региона, изменённые агентом вне ожидаемого.

    Ожидаемое состояние клетки без постройки: блок сцены или чистый мир. Клетки
    из exclude (ожидаемые блоки или найденные структуры) не проверяются. Блок сцены
    с пометкой removable можно сломать, но нельзя заменить другим блоком. Блоки
    сравниваются через Knowledge.block_matches, чтобы сундук, который сам
    повернулся, не считался изменением. Блоки робота (ROBOT_BLOCKS) пропускаются.
    """
    candidates = set(snap.changed()) | set(scene)
    out = []
    for p in sorted(candidates):
        if p in exclude or not snap.box.contains(p):
            continue
        actual = snap.get(p)
        if actual[0] in ROBOT_BLOCKS:
            continue
        want = scene.get(p, baseline_block(p[1]))
        if k.block_matches(want, actual):
            continue
        if p in removable and actual == AIR:
            continue
        out.append((p, actual))
    return out


def block_json(b: Block) -> str:
    """Блок строкой для отчётов."""
    return format_block(b)
