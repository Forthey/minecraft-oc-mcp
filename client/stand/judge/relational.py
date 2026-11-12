"""Судья режима relational: ищет постройки по шаблону и проверяет их положение.

Порядок: структуры обрабатываются в порядке файла сценария (проверка сценария
гарантирует, что ссылки идут только назад). Структура с anchor ищется среди
размещений, удовлетворяющих anchor. Структура с relative_to проверяется в точке
сдвига от найденной структуры-основы, затем в точках accept_also, затем ищется по
всему региону, и тогда судья сообщает фактический сдвиг.
"""

from __future__ import annotations

from stand.judge.common import extra_cells
from stand.judge.patterns import Placement, candidates, place
from stand.knowledge import Knowledge
from stand.scenario import Scenario
from stand.world.blocks import Pos
from stand.world.snapshot import Snapshot

DIRS: dict[str, Pos] = {
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "east": (1, 0, 0),
    "west": (-1, 0, 0),
    "up": (0, 1, 0),
    "down": (0, -1, 0),
}


def _dot(a: Pos, b: Pos) -> int:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: Pos, b: Pos) -> Pos:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Pos, b) -> Pos:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _manhattan(a: Pos, b: Pos) -> int:
    return sum(abs(v) for v in _sub(a, b))


class _Ctx:
    def __init__(self, snap: Snapshot, scenario: Scenario, k: Knowledge):
        self.snap = snap
        self.k = k
        self.start = scenario.robot["pos"]
        self.facing = scenario.robot["facing"]
        self.pass_accuracy = scenario.scoring["pass_accuracy"]
        scene = scenario.scene_blocks()
        # Изменения агента: клетки, где мир отличается от сцены и чистого мира.
        self.changed = dict(extra_cells(snap, scene, scenario.removable, set(), k))
        self.claimed: set[Pos] = set()

    def accuracy(self, pl: Placement) -> float:
        cells = pl.cells
        hits = sum(
            1 for p, want in cells
            if p not in self.claimed and self.k.block_matches(want, self.snap.get(p))
        )
        return hits / len(cells) if cells else 0.0

    def free_changed(self) -> dict[Pos, tuple]:
        return {p: b for p, b in self.changed.items() if p not in self.claimed}


def _anchor_ok(ctx: _Ctx, anchor: dict, pl: Placement) -> bool:
    cells = [p for p, _ in pl.cells]
    if "in_front_of_robot" in anchor:
        a = anchor["in_front_of_robot"]
        f = DIRS[ctx.facing]
        lat = (-f[2], 0, f[0])
        rel = [_sub(c, ctx.start) for c in cells]
        d = min(_dot(r, f) for r in rel)
        return a["min"] <= d <= a["max"] and any(abs(_dot(r, lat)) <= a.get("lateral", 0) for r in rel)
    if "near_block" in anchor:
        a = anchor["near_block"]
        base = tuple(a["pos"])
        s = DIRS[a["side"]]
        reach = {_add(base, (s[0] * n, s[1] * n, s[2] * n)) for n in range(1, 2 + a.get("max_gap", 0))}
        return bool(reach & set(cells)) and all(_dot(_sub(c, base), s) >= 1 for c in cells)
    if "absolute" in anchor:
        a = anchor["absolute"]
        return pl.origin == tuple(a["origin"]) and pl.rotation == a.get("rotation", 0)
    raise ValueError(f"unknown anchor {anchor}")


def _best(ctx: _Ctx, options: list[Placement]) -> tuple[Placement | None, float]:
    best, best_key = None, None
    for pl in options:
        acc = ctx.accuracy(pl)
        key = (-acc, _manhattan(pl.origin, ctx.start), pl.origin, pl.rotation)
        if best_key is None or key < best_key:
            best, best_key = pl, key
    return best, (-best_key[0] if best_key else 0.0)


def _locate_anchor(ctx, pattern, rotations, anchor):
    if "absolute" in anchor:
        a = anchor["absolute"]
        pl = place(pattern, a.get("rotation", 0), tuple(a["origin"]))
        return pl, ctx.accuracy(pl), True
    options = list(candidates(pattern, rotations, ctx.free_changed()))
    good = [pl for pl in options if _anchor_ok(ctx, anchor, pl)]
    pl, acc = _best(ctx, good)
    if pl is not None and acc > 0:
        return pl, acc, True
    pl, acc = _best(ctx, options)
    return pl, acc, False


def _locate_relative(ctx, pattern, rotations, st, base: Placement | None):
    rel = st["relative_to"]
    labelled = [("offset", rel["offset"])] + [(a["label"], a["offset"]) for a in st.get("accept_also", [])]
    best = (None, 0.0, "other", None)
    if base is not None:
        for label, off in labelled:
            origin = _add(base.origin, off)
            for rot in rotations:
                pl = place(pattern, rot, origin)
                acc = ctx.accuracy(pl)
                if acc > best[1]:
                    best = (pl, acc, label, list(off))
        if best[1] >= ctx.pass_accuracy:
            return best
    pl, acc = _best(ctx, list(candidates(pattern, rotations, ctx.free_changed())))
    if pl is not None and acc > best[1]:
        offset = list(_sub(pl.origin, base.origin)) if base is not None else None
        return pl, acc, "other", offset
    if best[0] is not None and best[1] > 0:
        return best
    return None, 0.0, "other", None


def judge_relational(snap: Snapshot, scenario: Scenario, k: Knowledge) -> dict:
    """Вердикт режима relational в сериализуемом виде.

    Для каждой структуры: found, origin, rotation, accuracy, anchor_ok (None без
    anchor), interpretation и offset (None без relative_to). Общая accuracy это
    доля совпавших клеток по всем структурам.
    """
    ctx = _Ctx(snap, scenario, k)
    patterns = scenario.structure_patterns()
    placed: dict[str, Placement | None] = {}
    rotation_of: dict[str, int] = {}
    report: dict[str, dict] = {}
    total_cells = matched_cells = 0

    for st in scenario.expected["structures"]:
        sid = st["id"]
        pattern = patterns[sid]
        src = st["pattern"].get("same_as")
        if "rotations" in st:
            rotations = st["rotations"]
        elif src is not None and src in rotation_of:
            rotations = [rotation_of[src]]
        else:
            rotations = [0]

        anchor_ok = interpretation = offset = None
        if "anchor" in st:
            pl, acc, anchor_ok = _locate_anchor(ctx, pattern, rotations, st["anchor"])
        else:
            base = placed.get(st["relative_to"]["structure"])
            pl, acc, interpretation, offset = _locate_relative(ctx, pattern, rotations, st, base)

        found = pl is not None and acc >= ctx.pass_accuracy
        placed[sid] = pl
        if pl is not None:
            rotation_of[sid] = pl.rotation
            if acc > 0:
                ctx.claimed.update(p for p, _ in pl.cells)
        total_cells += len(pattern)
        matched_cells += round(acc * len(pattern))
        report[sid] = {
            "found": found,
            "origin": list(pl.origin) if pl is not None and acc > 0 else None,
            "rotation": pl.rotation if pl is not None and acc > 0 else None,
            "accuracy": acc,
            "anchor_ok": anchor_ok,
            "interpretation": interpretation,
            "offset": offset,
        }

    extra = [
        {"pos": list(p), "actual": f"{b[0]}:{b[1]}" if b[1] else b[0]}
        for p, b in extra_cells(snap, scenario.scene_blocks(), scenario.removable, ctx.claimed, k)
    ]
    accuracy = matched_cells / total_cells if total_cells else 1.0
    passed = (
        all(r["found"] for r in report.values())
        and all(r["anchor_ok"] is not False for r in report.values())
        and all(r["interpretation"] != "other" for r in report.values())
        and len(extra) <= scenario.scoring["max_extra"]
    )
    return {"structures": report, "extra": extra, "accuracy": accuracy, "passed": passed}
