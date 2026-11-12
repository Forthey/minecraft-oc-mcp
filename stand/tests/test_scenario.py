import pytest
import yaml

from stand.config import load_config
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import (
    SCENARIOS_DIR,
    ScenarioError,
    check_scenario,
    expand_fill,
    list_scenarios,
    load_scenario,
    required_items,
)

BASE = {
    "id": "t-wall",
    "title": "test wall",
    "goal": "Build a 3x3 cobblestone wall.",
    "region": {"from": [90, 63, 90], "to": [115, 72, 110]},
    "robot": {"pos": [100, 64, 105], "facing": "north"},
    "warehouse": {"pos": [95, 64, 105], "side": "east", "items": {"minecraft:cobblestone": 9}},
    "expected": {"mode": "fixed", "fill": [
        {"from": [100, 64, 100], "to": [102, 66, 100], "block": "minecraft:cobblestone"}
    ]},
    "timeout_s": 600,
}


def _write(tmp_path, data):
    d = tmp_path / data["id"]
    d.mkdir(exist_ok=True)
    path = d / "scenario.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _check(tmp_path, **override):
    data = {**BASE, **override}
    s = load_scenario(_write(tmp_path, data))
    return check_scenario(s, Knowledge.load(KNOWLEDGE_DIR, s.knowledge), load_config())


def test_all_scenarios_valid():
    paths = list_scenarios(SCENARIOS_DIR)
    assert {p.parent.name for p in paths} >= {
        "s01-wall", "s02-craft", "s03-obstacle", "s04-ic2-machines",
        "s05-connection-lost", "s06-reactor-structure", "s07-relative", "s08-landmark",
    }
    cfg = load_config()
    for path in paths:
        s = load_scenario(path)
        assert s.id == path.parent.name
        assert check_scenario(s, Knowledge.load(KNOWLEDGE_DIR, s.knowledge), cfg) == [], s.id


def test_base_is_valid(tmp_path):
    assert _check(tmp_path) == []


def test_defaults(tmp_path):
    s = load_scenario(_write(tmp_path, BASE))
    assert s.profile == "full"
    assert s.scoring == {"pass_accuracy": 1.0, "max_extra": 0}
    assert s.robot["energy"] == 1.0 and s.robot["inventory"] == []
    assert s.faults == [] and s.requires == []


def test_schema_error_is_reported(tmp_path):
    with pytest.raises(ScenarioError, match="profile"):
        load_scenario(_write(tmp_path, {**BASE, "profile": "x-ray"}))


def test_region_outside_spawn_rejected(tmp_path):
    errors = _check(
        tmp_path,
        region={"from": [290, 63, 90], "to": [315, 72, 110]},
        robot={"pos": [300, 64, 105], "facing": "north"},
        warehouse={"pos": [295, 64, 105], "side": "east", "items": {"minecraft:cobblestone": 9}},
        expected={"mode": "fixed", "fill": [{"pos": [300, 64, 100], "block": "minecraft:cobblestone"}]},
    )
    assert any("spawn" in e for e in errors), errors


def test_unreachable_expected_rejected(tmp_path):
    errors = _check(
        tmp_path,
        warehouse={"pos": [95, 64, 105], "side": "east", "items": {"minecraft:cobblestone": 5}},
    )
    assert any("minecraft:cobblestone" in e and "4" in e for e in errors), errors


def test_craftable_expected_accepted(tmp_path):
    errors = _check(
        tmp_path,
        warehouse={"pos": [95, 64, 105], "side": "east", "items": {"minecraft:log": 1}},
        expected={"mode": "fixed", "fill": [
            {"from": [100, 64, 100], "to": [101, 64, 101], "block": "minecraft:planks"}
        ]},
    )
    assert errors == []


def test_expand_fill_counts():
    blocks = expand_fill([{"from": [0, 0, 0], "to": [2, 2, 0], "block": "minecraft:cobblestone"}])
    assert len(blocks) == 9
    assert blocks[(2, 2, 0)] == ("minecraft:cobblestone", 0)


def test_expand_fill_later_overrides():
    blocks = expand_fill([
        {"from": [0, 0, 0], "to": [2, 0, 0], "block": "minecraft:stone"},
        {"pos": [1, 0, 0], "block": "minecraft:planks:1"},
    ])
    assert blocks[(1, 0, 0)] == ("minecraft:planks", 1)
    assert blocks[(0, 0, 0)] == ("minecraft:stone", 0)


def test_robot_inside_region_and_air(tmp_path):
    outside = _check(tmp_path, robot={"pos": [80, 64, 105], "facing": "north"})
    assert any("robot" in e for e in outside), outside
    blocked = _check(tmp_path, setup_blocks=[{"pos": [100, 64, 105], "block": "minecraft:stone"}])
    assert any("robot" in e for e in blocked), blocked


def test_unknown_block_rejected(tmp_path):
    errors = _check(
        tmp_path,
        expected={"mode": "fixed", "fill": [{"pos": [100, 64, 100], "block": "nomod:thing"}]},
    )
    assert any("nomod:thing" in e for e in errors), errors


def test_fault_tool_must_be_in_contract(tmp_path):
    errors = _check(tmp_path, faults=[{"tool": "teleport", "call": 1, "error": "TIMEOUT", "effect": "skipped"}])
    assert any("teleport" in e for e in errors), errors


def test_relational_references_checked(tmp_path):
    errors = _check(tmp_path, expected={"mode": "relational", "structures": [
        {"id": "B", "pattern": {"same_as": "A"}, "relative_to": {"structure": "A", "offset": [-5, 0, 0]}},
    ]})
    assert any("A" in e for e in errors), errors


def test_required_items_relational_counts_same_as():
    s = load_scenario(SCENARIOS_DIR / "s07-relative" / "scenario.yaml")
    k = Knowledge.load(KNOWLEDGE_DIR, s.knowledge)
    assert required_items(s, k) == {"minecraft:cobblestone": 18}


def test_scene_blocks_include_warehouse_chest():
    s = load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml")
    assert s.scene_blocks()[tuple(s.warehouse["pos"])] == ("minecraft:chest", 0)


def test_scenarios_documented():
    """Каждый сценарий описан в docs/stand-scenarios.md отдельным разделом."""
    doc = (SCENARIOS_DIR.parents[1] / "docs" / "stand-scenarios.md").read_text(encoding="utf-8")
    for path in list_scenarios(SCENARIOS_DIR):
        sid = path.parent.name
        assert f"### {sid}:" in doc, f"scenario {sid} is not described in docs/stand-scenarios.md"
