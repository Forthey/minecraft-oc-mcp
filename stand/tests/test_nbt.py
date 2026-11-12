import pytest

from stand.world.nbt import (
    NbtError,
    TagByte,
    TagByteArray,
    TagDouble,
    TagFloat,
    TagIntArray,
    TagList,
    TagLong,
    TagShort,
    read_nbt,
    write_nbt,
)


def test_roundtrip_all_tag_types():
    root = {
        "b": TagByte(-5),
        "s": TagShort(-300),
        "i": 70000,
        "l": TagLong(2**40),
        "f": TagFloat(1.5),
        "d": TagDouble(2.25),
        "ba": TagByteArray(b"\x01\x02\xff"),
        "str": "\x01minecraft:stone",
        "list": [{"K": "a", "V": 1}, {"K": "b", "V": 2}],
        "empty": TagList(10, []),
        "nested": {"inner": {"x": 1}},
        "ia": TagIntArray([1, -2, 3]),
    }
    back = read_nbt(write_nbt(root))
    assert back == {
        "b": -5,
        "s": -300,
        "i": 70000,
        "l": 2**40,
        "f": 1.5,
        "d": 2.25,
        "ba": b"\x01\x02\xff",
        "str": "\x01minecraft:stone",
        "list": [{"K": "a", "V": 1}, {"K": "b", "V": 2}],
        "empty": [],
        "nested": {"inner": {"x": 1}},
        "ia": [1, -2, 3],
    }


@pytest.mark.parametrize("compression", ["gzip", "zlib", "none"])
def test_zlib_and_gzip(compression):
    assert read_nbt(write_nbt({"a": 1}, compression=compression)) == {"a": 1}


def test_garbage_raises_nbt_error():
    with pytest.raises(NbtError):
        read_nbt(b"\x78\x9cgarbage")
