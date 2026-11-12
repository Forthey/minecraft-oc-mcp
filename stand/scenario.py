"""Сценарии стенда: загрузка, проверка схемы и смысловая проверка.

Схема формата лежит в stand/scenario-schema.json, примеры в stand/scenarios/.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml

from stand.config import Config
from stand.knowledge import Knowledge, normalize_id
from stand.world.blocks import AIR, FLOOR_Y, Block, Pos, parse_block
from stand.world.snapshot import Box

STAND_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = STAND_DIR / "scenarios"
SCHEMA_PATH = STAND_DIR / "scenario-schema.json"
CONTRACT_PATH = STAND_DIR.parent / "agent" / "skills" / "references" / "tool-contract.md"
WAREHOUSE_BLOCK: Block = ("minecraft:chest", 0)
DEFAULT_SCORING = {"pass_accuracy": 1.0, "max_extra": 0}


class ScenarioError(ValueError):
    """Файл сценария не прошёл схему."""


@dataclass
class Scenario:
    """Загруженный сценарий. Позиции уже кортежи, блоки разобраны."""

    id: str
    title: str
    goal: str
    region: Box
    robot: dict
    warehouse: dict
    setup_blocks: dict[Pos, Block]
    removable: set[Pos]
    knowledge: dict
    profile: str
    faults: list[dict]
    requires: list[str]
    expected: dict
    scoring: dict
    timeout_s: int
    path: Path
    raw: dict = field(repr=False, default_factory=dict)

    def scene_blocks(self) -> dict[Pos, Block]:
        """Блоки, которые стенд ставит до запуска агента: setup_blocks и сундук склада."""
        blocks = dict(self.setup_blocks)
        blocks[tuple(self.warehouse["pos"])] = WAREHOUSE_BLOCK
        return blocks

    def fixed_expected(self) -> dict[Pos, Block]:
        """Ожидаемые блоки режима fixed. Для relational пусто."""
        if self.expected["mode"] != "fixed":
            return {}
        return expand_fill(self.expected["fill"])

    def structure_patterns(self) -> dict[str, dict[Pos, Block]]:
        """Шаблоны структур режима relational по id, same_as уже раскрыт."""
        if self.expected["mode"] != "relational":
            return {}
        out: dict[str, dict[Pos, Block]] = {}
        for st in self.expected["structures"]:
            pattern = st["pattern"]
            if "fill" in pattern:
                out[st["id"]] = expand_fill(pattern["fill"])
            elif pattern["same_as"] in out:
                out[st["id"]] = dict(out[pattern["same_as"]])
        return out


def _pos(v) -> Pos:
    return (int(v[0]), int(v[1]), int(v[2]))


def expand_fill(items: list[dict]) -> dict[Pos, Block]:
    """Разворачивает список {pos, block} и {from, to, block} в блоки. Поздние перекрывают ранние."""
    out: dict[Pos, Block] = {}
    for it in items:
        block = parse_block(it["block"])
        if "pos" in it:
            out[_pos(it["pos"])] = block
        else:
            for p in Box(_pos(it["from"]), _pos(it["to"])).iter():
                out[p] = block
    return out


def _removable(items: list[dict]) -> set[Pos]:
    out: set[Pos] = set()
    for it in items:
        if not it.get("removable"):
            continue
        if "pos" in it:
            out.add(_pos(it["pos"]))
        else:
            out.update(Box(_pos(it["from"]), _pos(it["to"])).iter())
    return out


def _validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def load_scenario(path: Path) -> Scenario:
    """Читает и проверяет по схеме файл сценария."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    errors = sorted(_validator().iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]
        raise ScenarioError(f"{path}: " + "; ".join(lines))
    robot = {
        "pos": _pos(data["robot"]["pos"]),
        "facing": data["robot"]["facing"],
        "energy": float(data["robot"].get("energy", 1.0)),
        "inventory": [
            {"item": normalize_id(i["item"]), "count": int(i["count"])}
            for i in data["robot"].get("inventory", [])
        ],
    }
    wh = data["warehouse"]
    warehouse = {
        "pos": _pos(wh["pos"]),
        "side": wh["side"],
        "items": {normalize_id(k): int(v) for k, v in wh["items"].items()},
    }
    setup = data.get("setup_blocks", [])
    return Scenario(
        id=data["id"],
        title=data["title"],
        goal=data["goal"].strip(),
        region=Box(_pos(data["region"]["from"]), _pos(data["region"]["to"])),
        robot=robot,
        warehouse=warehouse,
        setup_blocks=expand_fill(setup),
        removable=_removable(setup),
        knowledge=data.get("knowledge", {}),
        profile=data.get("profile", "full"),
        faults=list(data.get("faults", [])),
        requires=list(data.get("requires", [])),
        expected=data["expected"],
        scoring={**DEFAULT_SCORING, **data.get("scoring", {})},
        timeout_s=int(data["timeout_s"]),
        path=Path(path).resolve(),
        raw=data,
    )


def list_scenarios(root: Path = SCENARIOS_DIR) -> list[Path]:
    """Файлы scenario.yaml в подпапках root, по имени папки."""
    return sorted(root.glob("*/scenario.yaml"))


def required_items(s: Scenario, k: Knowledge) -> dict[str, int]:
    """Сколько каких предметов нужно, чтобы поставить все ожидаемые блоки.

    Блоки, для которых нет предмета, пропускаются (их ловит check_scenario).
    """
    blocks: list[Block] = list(s.fixed_expected().values())
    for pattern in s.structure_patterns().values():
        blocks.extend(pattern.values())
    counts: Counter = Counter()
    for b in blocks:
        if b == AIR:
            continue
        item = k.item_for(b)
        if item is not None:
            counts[item] += 1
    return dict(counts)


def _contract_tools() -> set[str]:
    from agent.tools.validate_skills import contract_tools

    return contract_tools(CONTRACT_PATH)


def check_scenario(s: Scenario, k: Knowledge, cfg: Config) -> list[str]:
    """Смысловые проверки сценария. Пустой список значит, что сценарий годен."""
    errors: list[str] = []
    sx, _, sz = cfg.spawn
    r = cfg.spawn_radius
    (x0, _, z0), (x1, _, z1) = s.region.lo, s.region.hi
    if min(x0, x1) < sx - r or max(x0, x1) > sx + r or min(z0, z1) < sz - r or max(z0, z1) > sz + r:
        errors.append(
            f"region must stay within {r} blocks of spawn {cfg.spawn} by x and z "
            "(spawn chunks are the only ones always loaded)"
        )

    scene = s.scene_blocks()
    robot_pos = s.robot["pos"]
    if not s.region.contains(robot_pos):
        errors.append(f"robot position {robot_pos} is outside the region")
    if robot_pos[1] <= FLOOR_Y or scene.get(robot_pos, AIR) != AIR:
        errors.append(f"robot position {robot_pos} is not in the air")
    if not s.region.contains(s.warehouse["pos"]):
        errors.append(f"warehouse {s.warehouse['pos']} is outside the region")
    for p in s.setup_blocks:
        if not s.region.contains(p):
            errors.append(f"setup block {p} is outside the region")

    for p, b in s.fixed_expected().items():
        if not s.region.contains(p):
            errors.append(f"expected block {p} is outside the region")
        if p in scene and scene[p] != AIR and p not in s.removable:
            errors.append(f"expected block {p} overlaps a scene block")
    all_blocks = list(s.fixed_expected().values()) + [
        b for pat in s.structure_patterns().values() for b in pat.values()
    ]
    for b in sorted(set(all_blocks)):
        if b != AIR and k.item_for(b) is None:
            errors.append(f"expected block {b[0]}:{b[1]} has no item in knowledge")

    if s.expected["mode"] == "relational":
        seen: set[str] = set()
        for st in s.expected["structures"]:
            src = st["pattern"].get("same_as")
            if src is not None and src not in seen:
                errors.append(f"structure {st['id']}: same_as {src} is not defined before it")
            rel = st.get("relative_to")
            if rel is not None and rel["structure"] not in seen:
                errors.append(f"structure {st['id']}: relative_to {rel['structure']} is not defined before it")
            near = st.get("anchor", {}).get("near_block")
            if near is not None and _pos(near["pos"]) not in scene:
                errors.append(f"structure {st['id']}: near_block {near['pos']} is not a scene block")
            seen.add(st["id"])

    tools = _contract_tools()
    for f in s.faults:
        if f["tool"] not in tools:
            errors.append(f"fault tool {f['tool']} is not in the MCP contract")

    have = Counter(s.warehouse["items"])
    for it in s.robot["inventory"]:
        have[it["item"]] += it["count"]
    needs = required_items(s, k)
    if needs:
        for m in k.plan_many(needs, dict(have))["missing"]:
            errors.append(
                f"expected needs {m['count']} more {m['item']}: not in warehouse or inventory"
                + (" and its recipe cannot be expanded" if m["craftable"] else " and not craftable")
            )
    return errors
