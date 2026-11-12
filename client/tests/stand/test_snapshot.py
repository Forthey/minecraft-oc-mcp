from stand.world.anvil import write_region
from stand.world.blocks import AIR, baseline_block, parse_block
from stand.world.nbt import TagByteArray, TagList, write_nbt
from stand.world.snapshot import Box, Snapshot, read_snapshot

# Числовые id синтетического мира. 600 проверяет старшие биты из Add.
IDS = {
    0: "minecraft:air",
    1: "minecraft:stone",
    2: "minecraft:grass",
    3: "minecraft:dirt",
    4: "minecraft:cobblestone",
    7: "minecraft:bedrock",
    600: "IC2:blockMachine",
}
BY_NAME = {v: k for k, v in IDS.items()}


def _flat_column_blocks():
    """Блоки чистого плоского мира для одной колонки, y от 0 до 63."""
    return {y: baseline_block(y) for y in range(64)}


def _build_world(tmp_path, extra: dict, chunks):
    """Собирает мир: плоский пол во всех chunks плюс блоки extra {pos: "mod:name:meta"}."""
    world = tmp_path / "world"
    world.mkdir()
    item_data = [{"K": "\x01" + name, "V": i} for i, name in IDS.items()]
    item_data.append({"K": "\x02minecraft:stick", "V": 280})
    (world / "level.dat").write_bytes(write_nbt({"Data": {}, "FML": {"ItemData": item_data}}))

    columns = _flat_column_blocks()
    overrides = {}
    for pos, s in extra.items():
        overrides[pos] = parse_block(s)

    nbt_chunks = {}
    for cx, cz in chunks:
        sections = {}
        for sy in range(16):
            sections[sy] = (bytearray(4096), bytearray(2048), bytearray(2048))

        def put(x, y, z, block):
            sec = sections[y >> 4]
            i = (y & 15) * 256 + (z & 15) * 16 + (x & 15)
            block_id = BY_NAME[block[0]]
            sec[0][i] = block_id & 0xFF
            hi = block_id >> 8
            meta = block[1]
            for arr, val in ((sec[1], hi), (sec[2], meta)):
                j = i >> 1
                if i & 1:
                    arr[j] = (arr[j] & 0x0F) | (val << 4)
                else:
                    arr[j] = (arr[j] & 0xF0) | val

        for lx in range(16):
            for lz in range(16):
                for y, block in columns.items():
                    put(cx * 16 + lx, y, cz * 16 + lz, block)
        for (x, y, z), block in overrides.items():
            if x >> 4 == cx and z >> 4 == cz:
                put(x, y, z, block)
        section_list = []
        for sy, (blocks, add, data) in sections.items():
            if not any(blocks):
                continue
            section_list.append({
                "Y": sy,
                "Blocks": TagByteArray(bytes(blocks)),
                "Add": TagByteArray(bytes(add)),
                "Data": TagByteArray(bytes(data)),
            })
        nbt_chunks[(cx, cz)] = {"Level": {"xPos": cx, "zPos": cz, "Sections": TagList(10, section_list)}}
    write_region(world / "region", nbt_chunks)
    return world


def test_vanilla_block_read(tmp_path):
    world = _build_world(tmp_path, {(100, 64, 100): "minecraft:cobblestone"}, [(6, 6)])
    snap = read_snapshot(world, Box((96, 63, 96), (104, 66, 104)))
    assert snap.get((100, 64, 100)) == ("minecraft:cobblestone", 0)
    assert snap.changed() == {(100, 64, 100): ("minecraft:cobblestone", 0)}


def test_mod_block_with_add_and_meta(tmp_path):
    world = _build_world(tmp_path, {(101, 65, 99): "IC2:blockMachine:3"}, [(6, 6)])
    snap = read_snapshot(world, Box((96, 63, 96), (104, 66, 104)))
    assert snap.get((101, 65, 99)) == ("IC2:blockMachine", 3)


def test_baseline_not_in_changed(tmp_path):
    world = _build_world(tmp_path, {(98, 63, 98): "minecraft:air"}, [(6, 6)])
    snap = read_snapshot(world, Box((96, 60, 96), (104, 66, 104)))
    assert snap.get((97, 63, 97)) == ("minecraft:grass", 0)
    assert snap.changed() == {(98, 63, 98): AIR}


def test_region_across_boundaries(tmp_path):
    extra = {
        (-1, 64, -1): "minecraft:cobblestone",
        (0, 64, 0): "IC2:blockMachine:3",
        (511, 64, 5): "minecraft:stone",
        (512, 64, 5): "minecraft:cobblestone",
    }
    chunks = [(-1, -1), (0, 0), (-1, 0), (0, -1), (31, 0), (32, 0)]
    world = _build_world(tmp_path, extra, chunks)
    assert {p.name for p in (world / "region").iterdir()} >= {"r.-1.-1.mca", "r.0.0.mca", "r.1.0.mca"}
    snap = read_snapshot(world, Box((-2, 64, -2), (513, 64, 6)))
    for pos, s in extra.items():
        assert snap.get(pos) == parse_block(s), pos
    assert snap.get((-2, 64, -2)) == AIR


def test_missing_chunk_is_baseline(tmp_path):
    world = _build_world(tmp_path, {}, [(6, 6)])
    snap = read_snapshot(world, Box((200, 62, 200), (201, 64, 201)))
    assert snap.changed() == {}
    assert snap.get((200, 63, 200)) == ("minecraft:grass", 0)


def test_json_roundtrip(tmp_path):
    world = _build_world(tmp_path, {(100, 64, 100): "IC2:blockMachine:3"}, [(6, 6)])
    snap = read_snapshot(world, Box((96, 63, 96), (104, 66, 104)))
    back = Snapshot.from_json(snap.to_json())
    assert back.box == snap.box
    assert back.changed() == snap.changed()


def test_box_normalizes_corners():
    box = Box((5, 70, 5), (1, 64, 3))
    assert box.lo == (1, 64, 3) and box.hi == (5, 70, 5)
    assert box.contains((1, 64, 3)) and not box.contains((0, 64, 3))
    assert len(list(box.iter())) == 5 * 7 * 3


def test_real_template_is_clean_flat_world():
    """Шаблон мира стенда (если создан) читается как чистый плоский мир."""
    import pytest

    from stand.config import load_config

    template = load_config().world_template_dir
    if not (template / "level.dat").exists():
        pytest.skip("world template not created, run python -m stand.server setup")
    # Ниже y=60 лежит камень, и в нём AE2 и Forestry генерируют руды. Регионы сценариев
    # начинаются с пола (y=63), поэтому проверяется только слой земли и выше.
    snap = read_snapshot(template, Box((-20, 60, -20), (-1, 80, -1)))
    assert snap.changed() == {}
