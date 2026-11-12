"""Чтение и запись NBT (формат Minecraft 1.7.10, теги 0..11).

При чтении compound становится dict, list становится list, ByteArray это bytes,
IntArray это list[int]. При записи тип числа задаётся обёртками TagByte, TagShort
и т.п. Голый int пишется как Int, float как Double, list как List с типом
по первому элементу.
"""

from __future__ import annotations

import gzip
import io
import struct
import zlib
from dataclasses import dataclass

END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LIST, COMPOUND, INT_ARRAY = range(12)


@dataclass
class TagByte:
    value: int


@dataclass
class TagShort:
    value: int


@dataclass
class TagInt:
    value: int


@dataclass
class TagLong:
    value: int


@dataclass
class TagFloat:
    value: float


@dataclass
class TagDouble:
    value: float


@dataclass
class TagByteArray:
    value: bytes


@dataclass
class TagIntArray:
    value: list


@dataclass
class TagList:
    """Список с явным типом элементов (нужен для пустых списков)."""

    tag: int
    items: list


class NbtError(ValueError):
    """Повреждённые или неподдерживаемые данные NBT."""


def _decompress(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    if data[:1] == b"\x0a":
        return data
    try:
        return zlib.decompress(data)
    except zlib.error as e:
        raise NbtError(f"cannot decompress NBT: {e}") from e


class _Reader:
    def __init__(self, data: bytes):
        self.buf = io.BytesIO(data)

    def take(self, n: int) -> bytes:
        b = self.buf.read(n)
        if len(b) != n:
            raise NbtError("unexpected end of NBT data")
        return b

    def unpack(self, fmt: str):
        return struct.unpack(">" + fmt, self.take(struct.calcsize(">" + fmt)))[0]

    def string(self) -> str:
        n = self.unpack("H")
        return self.take(n).decode("utf-8", errors="replace")

    def payload(self, tag: int):
        if tag == BYTE:
            return self.unpack("b")
        if tag == SHORT:
            return self.unpack("h")
        if tag == INT:
            return self.unpack("i")
        if tag == LONG:
            return self.unpack("q")
        if tag == FLOAT:
            return self.unpack("f")
        if tag == DOUBLE:
            return self.unpack("d")
        if tag == BYTE_ARRAY:
            return self.take(self.unpack("i"))
        if tag == STRING:
            return self.string()
        if tag == LIST:
            elem = self.unpack("b")
            n = self.unpack("i")
            return [self.payload(elem) for _ in range(n)]
        if tag == COMPOUND:
            out = {}
            while True:
                t = self.unpack("b")
                if t == END:
                    return out
                name = self.string()
                out[name] = self.payload(t)
        if tag == INT_ARRAY:
            n = self.unpack("i")
            return list(struct.unpack(f">{n}i", self.take(4 * n)))
        raise NbtError(f"unknown NBT tag {tag}")


def read_nbt(data: bytes) -> dict:
    """Читает корневой compound. Сжатие gzip или zlib определяется по данным."""
    r = _Reader(_decompress(data))
    tag = r.unpack("b")
    if tag != COMPOUND:
        raise NbtError(f"root tag is {tag}, expected compound")
    r.string()
    return r.payload(COMPOUND)


def _tag_of(v) -> int:
    if isinstance(v, TagByte):
        return BYTE
    if isinstance(v, TagShort):
        return SHORT
    if isinstance(v, (TagInt, int)):
        return INT
    if isinstance(v, TagLong):
        return LONG
    if isinstance(v, TagFloat):
        return FLOAT
    if isinstance(v, (TagDouble, float)):
        return DOUBLE
    if isinstance(v, (TagByteArray, bytes, bytearray)):
        return BYTE_ARRAY
    if isinstance(v, str):
        return STRING
    if isinstance(v, (TagList, list)):
        return LIST
    if isinstance(v, dict):
        return COMPOUND
    if isinstance(v, TagIntArray):
        return INT_ARRAY
    raise TypeError(f"cannot write {type(v).__name__} as NBT")


def _write_string(out: io.BytesIO, s: str) -> None:
    b = s.encode("utf-8")
    out.write(struct.pack(">H", len(b)) + b)


def _write_payload(out: io.BytesIO, v) -> None:
    tag = _tag_of(v)
    raw = getattr(v, "value", v)
    if tag == BYTE:
        out.write(struct.pack(">b", raw))
    elif tag == SHORT:
        out.write(struct.pack(">h", raw))
    elif tag == INT:
        out.write(struct.pack(">i", raw))
    elif tag == LONG:
        out.write(struct.pack(">q", raw))
    elif tag == FLOAT:
        out.write(struct.pack(">f", raw))
    elif tag == DOUBLE:
        out.write(struct.pack(">d", raw))
    elif tag == BYTE_ARRAY:
        out.write(struct.pack(">i", len(raw)) + bytes(raw))
    elif tag == STRING:
        _write_string(out, raw)
    elif tag == LIST:
        if isinstance(v, TagList):
            elem, items = v.tag, v.items
        else:
            items = v
            elem = _tag_of(items[0]) if items else END
        out.write(struct.pack(">bi", elem, len(items)))
        for item in items:
            _write_payload(out, item)
    elif tag == COMPOUND:
        for name, item in v.items():
            out.write(struct.pack(">b", _tag_of(item)))
            _write_string(out, name)
            _write_payload(out, item)
        out.write(b"\x00")
    elif tag == INT_ARRAY:
        out.write(struct.pack(f">i{len(raw)}i", len(raw), *raw))


def write_nbt(root: dict, compression: str = "gzip") -> bytes:
    """Пишет корневой compound с пустым именем. compression: gzip, zlib или none."""
    out = io.BytesIO()
    out.write(struct.pack(">b", COMPOUND))
    _write_string(out, "")
    _write_payload(out, root)
    data = out.getvalue()
    if compression == "gzip":
        return gzip.compress(data)
    if compression == "zlib":
        return zlib.compress(data)
    return data
