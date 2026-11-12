import copy
import json
from pathlib import Path


from stand.fake_mcp.action_log import ActionLog
from stand.fake_mcp.dispatch import TOOL_SPECS, Dispatcher
from stand.fake_mcp.profiles import PROFILES
from stand.fake_mcp.sim import USED_CODES, RobotSim
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.scenario import SCENARIOS_DIR, load_scenario
from stand.world.backend import MemoryWorld
from agent.tools.validate_skills import contract_error_codes, contract_tools

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "agent" / "skills" / "references" / "tool-contract.md"


def _dispatcher(tmp_path, sid="s01-wall", profile="full", faults=None, inventory=None):
    s = copy.deepcopy(load_scenario(SCENARIOS_DIR / sid / "scenario.yaml"))
    s.robot["inventory"] = inventory if inventory is not None else [{"item": "minecraft:cobblestone", "count": 16}]
    world = MemoryWorld(s.scene_blocks())
    sim = RobotSim(s, Knowledge.load(KNOWLEDGE_DIR, s.knowledge), world)
    log = ActionLog(tmp_path / "action_log.jsonl")
    d = Dispatcher(sim, profile, faults if faults is not None else s.faults, log)
    return d, world, log


def test_tool_specs_match_contract():
    assert set(TOOL_SPECS) == contract_tools(CONTRACT)


def test_groups_cover_contract_sections():
    assert {spec.group for spec in TOOL_SPECS.values()} == {
        "state", "movement", "world", "inventory", "crafting", "knowledge", "verification", "service",
    }


def test_error_codes_subset():
    assert USED_CODES <= contract_error_codes(CONTRACT)


def test_profiles_reference_known_tools():
    assert set(PROFILES) == {"full", "no-vision", "no-docs", "no-nei"}
    for name, profile in PROFILES.items():
        assert set(profile) == {"disabled", "no_provider"}, name
        assert profile["disabled"] | profile["no_provider"] <= set(TOOL_SPECS), name


def test_profile_hides_tools(tmp_path):
    d, _, _ = _dispatcher(tmp_path, profile="no-vision")
    enabled = set(d.enabled_tools())
    assert not enabled & {"surroundings", "geo_scan"}
    assert len(enabled) == 26
    r = d.call("surroundings", {})
    assert r["error_code"] == "BLOCKED" and "not available" in r["message"]


def test_no_nei_profile_returns_no_provider(tmp_path):
    d, _, _ = _dispatcher(tmp_path, profile="no-nei")
    assert len(d.enabled_tools()) == len(TOOL_SPECS)
    for name, args in [("nei_find", {"text": "stone"}), ("craft_recipe", {"recipe": "r0000000000000000"})]:
        r = d.call(name, args)
        assert r["error_code"] == "NO_PROVIDER", name
        assert r["message"] == "NO_PROVIDER: no player with the mod is online and the answer is not cached"
    assert d.call("get_status", {})["ok"]


def test_fault_applied(tmp_path):
    faults = [{"tool": "place_at", "call": 5, "error": "CONNECTION_LOST", "effect": "applied"}]
    d, world, log = _dispatcher(tmp_path, faults=faults)
    results = [d.call("place_at", {"x": 100 + i, "y": 64, "z": 100, "item": "minecraft:cobblestone"}) for i in range(5)]
    assert all(r["ok"] for r in results[:4])
    assert results[4]["error_code"] == "CONNECTION_LOST"
    assert world.get((104, 64, 100)) == ("minecraft:cobblestone", 0)
    assert log.entries[4]["fault"] is True and log.entries[3]["fault"] is False


def test_fault_skipped(tmp_path):
    faults = [{"tool": "place_at", "call": 1, "error": "TIMEOUT", "effect": "skipped"}]
    d, world, _ = _dispatcher(tmp_path, faults=faults)
    r = d.call("place_at", {"x": 100, "y": 64, "z": 100, "item": "minecraft:cobblestone"})
    assert r["error_code"] == "TIMEOUT"
    assert world.get((100, 64, 100)) == ("minecraft:air", 0)
    # Повтор уже без сбоя.
    assert d.call("place_at", {"x": 100, "y": 64, "z": 100, "item": "minecraft:cobblestone"})["ok"]


def test_log_line_shape(tmp_path):
    d, _, log = _dispatcher(tmp_path)
    d.call("move_to", {"x": 100, "y": 64, "z": 101})
    lines = (tmp_path / "action_log.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    assert set(entry) == {"ts", "tool", "args", "ok", "error_code", "duration_ms", "fault", "data"}
    assert entry["tool"] == "move_to" and entry["ok"] is True and entry["error_code"] is None
    assert entry["data"]["pos"] == [100, 64, 101] and entry["data"]["dug"] == []


def test_from_argument_mapped(tmp_path):
    d, _, _ = _dispatcher(tmp_path)
    r = d.call("place_at", {"x": 100, "y": 64, "z": 100, "item": "minecraft:cobblestone", "from": "up"})
    assert r["ok"], r
    assert d.sim.pos == (100, 65, 100)  # подход сверху, как просили в from


def test_bad_arguments(tmp_path):
    d, _, log = _dispatcher(tmp_path)
    r = d.call("move_to", {"x": "far"})
    assert r["error_code"] == "BLOCKED" and "argument" in r["message"]
    assert len(log.entries) == 1


def test_unknown_tool(tmp_path):
    d, _, _ = _dispatcher(tmp_path)
    assert d.call("teleport", {})["error_code"] == "BLOCKED"


def test_internal_error_envelope(tmp_path, monkeypatch):
    d, _, _ = _dispatcher(tmp_path)

    def boom(*a, **kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(d.sim, "get_status", boom)
    r = d.call("get_status", {})
    assert r["error_code"] == "BLOCKED" and "internal error" in r["message"]


def test_get_action_log(tmp_path):
    d, _, _ = _dispatcher(tmp_path)
    d.call("get_status", {})
    d.call("move_to", {"x": 200, "y": 64, "z": 100})
    r = d.call("get_action_log", {"last_n": 5})
    actions = r["data"]["actions"]
    assert [a["tool"] for a in actions] == ["get_status", "move_to"]
    assert actions[1]["error_code"] == "OUT_OF_RANGE"


def test_every_tool_callable(tmp_path):
    """Каждый tool контракта отвечает конвертом на минимальные аргументы."""
    d, _, _ = _dispatcher(tmp_path)
    minimal = {
        "get_status": {}, "world_info": {}, "surroundings": {}, "geo_scan": {"width": 2, "depth": 2},
        "move_to": {"x": 100, "y": 64, "z": 104}, "face": {"direction": "east"},
        "move": {"direction": "up"}, "turn": {"direction": "left"},
        "place_at": {"x": 100, "y": 64, "z": 100, "item": "minecraft:cobblestone"},
        "place": {"side": "front"}, "swing": {"side": "front"}, "use": {"side": "front"},
        "inventory_scan": {}, "inventory_transfer": {"from_slot": 1, "to_slot": 4},
        "storage_scan": {"side": "front"}, "storage_take": {"side": "front", "slot": 1},
        "storage_put": {"side": "front", "robot_slot": 1}, "equip": {"slot": 1},
        "craft_recipe": {"recipe": "r0000000000000000"}, "craft": {},
        "nei_find": {"text": "stone"}, "nei_recipes": {"item": "minecraft:chest"},
        "nei_recipe": {"recipe": "r0000000000000000"}, "nei_craft_tree": {"item": "minecraft:chest"},
        "nei_machine_plan": {"recipe": "r0000000000000000"}, "search_docs": {"query": "generator"},
        "verify_blocks": {"expected": [{"pos": [100, 64, 100], "item": "minecraft:cobblestone"}]},
        "get_action_log": {},
    }
    assert set(minimal) == set(TOOL_SPECS)
    for name, args in minimal.items():
        r = d.call(name, args)
        assert set(r) >= {"ok", "message", "data"}, name
        if not r["ok"]:
            assert r["error_code"] in USED_CODES, (name, r)
            assert "internal error" not in r["message"] and "argument" not in r["message"], (name, r)
