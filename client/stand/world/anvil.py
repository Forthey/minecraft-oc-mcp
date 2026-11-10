"""Чтение чанков из region-файлов (.mca) формата Anvil в варианте 1.7.10.

Region-файл покрывает 32x32 чанка. Первые 4096 байт: таблица смещений, по 4 байта
на чанк (3 байта номер сектора, 1 байт число секторов), индекс
(cx & 31) + (cz & 31) * 32. Чанк лежит с начала своего сектора: длина (int32 BE),
байт сжатия (1 gzip, 2 zlib), затем NBT.

Блоки чанка лежат в Level.Sections, секция на 16 блоков по высоте: Blocks (4096
байт, младшие 8 бит id), Add (2048, старшие 4 бита id, необязательно), Data
(2048, meta). Индекс в секции (y & 15) * 256 + z * 16 + x, у ниббла чётного
индекса младшие 4 бита.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Iterator

from stand.world.blocks import Pos
from stand.world.nbt import read_nbt, write_nbt

SECTOR = 4096


def region_path(region_dir: Path, cx: int, cz: int) -> Path:
    """Путь к region-файлу, в котором лежит чанк (cx, cz)."""
    return region_dir / f"r.{cx >> 5}.{cz >> 5}.mca"


def read_chunk(region_dir: Path, cx: int, cz: int) -> dict | None:
    """Возвращает NBT чанка или None, если чанк ещё не сгенерирован."""
    path = region_path(region_dir, cx, cz)
    if not path.exists():
        return None
    with open(path, "rb") as f:
        header = f.read(SECTOR)
        if len(header) < SECTOR:
            return None
        i = 4 * ((cx & 31) + (cz & 31) * 32)
        loc = int.from_bytes(header[i:i + 3], "big")
        if loc == 0:
            return None
        f.seek(loc * SECTOR)
        length, compression = struct.unpack(">ib", f.read(5))
        data = f.read(length - 1)
    if compression not in (1, 2):
        raise ValueError(f"chunk {cx},{cz}: unknown compression {compression}")
    return read_nbt(data)


def _nibble(arr: bytes, i: int) -> int:
    b = arr[i >> 1]
    return (b >> 4) & 0xF if i & 1 else b & 0xF


def section_block(section: dict, lx: int, ly: int, lz: int) -> tuple[int, int]:
    """Числовой id и meta блока в секции по локальным координатам 0..15."""
    i = ly * 256 + lz * 16 + lx
    block_id = section["Blocks"][i]
    add = section.get("Add")
    if add:
        block_id |= _nibble(add, i) << 8
    return block_id, _nibble(section["Data"], i)


def chunk_sections(chunk: dict) -> dict[int, dict]:
    """Секции чанка по номеру Y (0..15)."""
    return {s["Y"]: s for s in chunk["Level"].get("Sections", [])}


def chunk_blocks(chunk: dict) -> Iterator[tuple[Pos, int, int]]:
    """Все блоки чанка: мировая позиция, числовой id, meta."""
    level = chunk["Level"]
    bx, bz = level["xPos"] * 16, level["zPos"] * 16
    for sy, section in chunk_sections(chunk).items():
        for ly in range(16):
            for lz in range(16):
                for lx in range(16):
                    block_id, meta = section_block(section, lx, ly, lz)
                    yield (bx + lx, sy * 16 + ly, bz + lz), block_id, meta


def write_region(region_dir: Path, chunks: dict[tuple[int, int], dict]) -> None:
    """Пишет чанки в region-файлы. Нужен тестам для синтетических миров."""
    region_dir.mkdir(parents=True, exist_ok=True)
    by_file: dict[Path, list[tuple[int, int, dict]]] = {}
    for (cx, cz), nbt in chunks.items():
        by_file.setdefault(region_path(region_dir, cx, cz), []).append((cx, cz, nbt))
    for path, items in by_file.items():
        header = bytearray(SECTOR * 2)
        body = bytearray()
        sector = 2
        for cx, cz, nbt in items:
            data = zlib.compress(write_nbt(nbt, compression="none"))
            blob = struct.pack(">ib", len(data) + 1, 2) + data
            blob += b"\x00" * (-len(blob) % SECTOR)
            count = len(blob) // SECTOR
            i = 4 * ((cx & 31) + (cz & 31) * 32)
            header[i:i + 4] = sector.to_bytes(3, "big") + bytes([count])
            body += blob
            sector += count
        path.write_bytes(bytes(header) + bytes(body))
