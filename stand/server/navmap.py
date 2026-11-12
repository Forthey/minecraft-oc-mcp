"""Карта map_<id> масштаба 1 с центром (0, 0) для Navigation Upgrade.

Navigation Upgrade OpenComputers отдаёт координаты относительно центра карты, из
которой его скрафтили, и только в её пределах: при масштабе 1 это до 128 блоков от
центра по каждой оси. Карта с центром (0, 0) даёт абсолютные координаты на площадках
стенда у (100, 64, 100).

Карта пишется в мир сервера и в шаблон мира при остановленном сервере (setup делает
это сам). В игре: /give <ник> filled_map 1 <id>, затем скрафтить Navigation Upgrade.
Новая карта или карта из творческой вкладки не подойдут: координаты будут смещены.
"""

from __future__ import annotations

from pathlib import Path

from stand.world.nbt import TagByte, TagShort, read_nbt, write_nbt

SCALE = 1
CENTER = (0, 0)


def _is_nav_map(path: Path) -> bool:
    try:
        d = read_nbt(path.read_bytes())["data"]
    except (OSError, ValueError, KeyError):
        return False
    return d.get("scale") == SCALE and (d.get("xCenter"), d.get("zCenter")) == CENTER and d.get("dimension") == 0


def find_nav_map(world: Path) -> int | None:
    """Id карты стенда в мире или None."""
    ids = sorted(int(p.stem.split("_", 1)[1]) for p in (world / "data").glob("map_*.dat")
                 if p.stem.split("_", 1)[1].isdigit())
    return next((i for i in ids if _is_nav_map(world / "data" / f"map_{i}.dat")), None)


def _next_map_id(world: Path) -> int:
    idcounts = world / "data" / "idcounts.dat"
    if not idcounts.exists():
        return 0
    return int(read_nbt(idcounts.read_bytes()).get("map", -1)) + 1


def _write_map(world: Path, map_id: int) -> None:
    data_dir = world / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "data": {
            "dimension": TagByte(0),
            "scale": TagByte(SCALE),
            "width": TagShort(128),
            "height": TagShort(128),
            "xCenter": CENTER[0],
            "zCenter": CENTER[1],
            "colors": bytes(128 * 128),
        }
    }
    (data_dir / f"map_{map_id}.dat").write_bytes(write_nbt(payload, "gzip"))
    # idcounts.dat в 1.7.10 пишется без сжатия. Счётчик не уменьшаем, чтобы не затереть чужие карты.
    counter = max(map_id, _next_map_id(world) - 1)
    (data_dir / "idcounts.dat").write_bytes(write_nbt({"map": TagShort(counter)}, "none"))


def ensure_nav_map(worlds: list[Path]) -> int:
    """Одна и та же карта стенда во всех существующих мирах. Возвращает её id.

    Если в каком-то мире карта уже есть, берётся её id, иначе первый свободный во всех мирах.
    Повторный вызов ничего не меняет.
    """
    worlds = [w for w in worlds if w.exists()]
    if not worlds:
        raise FileNotFoundError("no world to write the navigation map into")
    found = [i for i in (find_nav_map(w) for w in worlds) if i is not None]
    map_id = found[0] if found else max(_next_map_id(w) for w in worlds)
    for w in worlds:
        if find_nav_map(w) != map_id:
            _write_map(w, map_id)
    return map_id
