"""Пишет в мир стенда карту map_<id> масштаба 1 с центром (0, 0).

Navigation Upgrade OpenComputers отдаёт координаты относительно центра карты, из
которой его скрафтили, и только в её пределах (±128 блоков при масштабе 1). Карта с
центром (0, 0) даёт абсолютные координаты на площадке стенда у (100, 64, 100).

Запускать при остановленном сервере:
  uv run python demo/make_nav_map.py        (из корня репозитория)
Затем в игре: /give <ник> filled_map 1 <id> и скрафтить Navigation Upgrade с этой картой.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from stand.world.nbt import TagByte, TagShort, read_nbt, write_nbt  # noqa: E402

WORLDS = [ROOT / "stand/server/instance/world", ROOT / "stand/server/world-template"]


def next_map_id(data_dir: Path) -> int:
    idcounts = data_dir / "idcounts.dat"
    if not idcounts.exists():
        return 0
    v = read_nbt(idcounts.read_bytes()).get("map")
    return int(getattr(v, "value", v)) + 1


def write_map(world: Path, map_id: int) -> None:
    data_dir = world / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "data": {
            "dimension": TagByte(0),
            "scale": TagByte(1),
            "width": TagShort(128),
            "height": TagShort(128),
            "xCenter": 0,
            "zCenter": 0,
            "colors": bytes(128 * 128),
        }
    }
    (data_dir / f"map_{map_id}.dat").write_bytes(write_nbt(payload, "gzip"))
    # idcounts.dat в 1.7.10 пишется без сжатия.
    (data_dir / "idcounts.dat").write_bytes(write_nbt({"map": TagShort(map_id)}, "none"))


def main() -> int:
    worlds = [w for w in WORLDS if w.exists()]
    map_id = max(next_map_id(w / "data") for w in worlds)
    for w in worlds:
        write_map(w, map_id)
        print(f"{w / 'data' / f'map_{map_id}.dat'}: scale 1, center (0, 0)")
    print(f"map id: {map_id}  ->  /give <ник> filled_map 1 {map_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
