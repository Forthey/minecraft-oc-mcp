from typing import Annotated, Literal

from schema import Range, Tool

Side = Literal["front", "up", "down"]
Slot = Annotated[int, Range(1)]
Count = Annotated[int, Range(1, 64)]


class Move(Tool):
    name = "move"
    description = ("Move the robot n blocks forward, back, up or down. "
                   "Stops at the first obstacle and reports how many steps were made.")
    timeout = 120

    direction: Literal["forward", "back", "up", "down"]
    n: Count = 1


class Turn(Tool):
    name = "turn"
    description = "Turn the robot left, right or around."

    direction: Literal["left", "right", "around"]


class InventoryScan(Tool):
    name = "inventory_scan"
    description = ("List non-empty slots of the robot inventory. "
                   "Item names are shown only if the robot has an inventory controller.")


class InventoryTransfer(Tool):
    name = "inventory_transfer"
    description = ("Move items between two slots of the robot inventory (all items if count is omitted). "
                   "The target slot must be empty or hold the same item; "
                   "a slot with a different item is refused, never swapped.")

    from_slot: Slot
    to_slot: Slot
    count: Count | None


class StorageScan(Tool):
    name = "storage_scan"
    description = ("List non-empty slots of a chest, furnace, machine or other storage next to the robot. "
                   "Also reports the block name (e.g. minecraft:furnace) if the robot has a geolyzer; "
                   "slot roles and which sides accept items depend on the block.")

    side: Side = "front"


class StorageTake(Tool):
    name = "storage_take"
    description = ("Take items from a slot of an adjacent storage into the robot inventory. "
                   "robot_slot selects the target slot, otherwise the selected one is used.")

    side: Side
    slot: Slot
    count: Count | None
    robot_slot: Slot | None


class StoragePut(Tool):
    name = "storage_put"
    description = ("Put items from a robot slot into an adjacent storage. "
                   "If slot is omitted, the storage picks the slot itself.")

    side: Side
    robot_slot: Slot
    count: Count | None
    slot: Slot | None


class Craft(Tool):
    name = "craft"
    description = ("Low-level crafting of whatever is already laid out in the robot crafting grid. "
                   "Prefer craft_recipe, which lays the grid out by itself from a NEI recipe id. "
                   "The inventory is 4 slots wide, so the grid is NOT slots 1-9 in a row. "
                   "Grid position -> inventory slot:\n"
                   "  [ 1][ 2][ 3]   (slots 4, 8, 12 and 13+ are outside the grid)\n"
                   "  [ 5][ 6][ 7]\n"
                   "  [ 9][10][11]\n"
                   "Example, iron pickaxe: ingots in 1,2,3; sticks in 6 and 10. "
                   "Arrange ingredients there with inventory_transfer first; "
                   "grid slots not used by the recipe must be empty. "
                   "count is how many crafts to do (default: as many as possible). "
                   "The result goes to result_slot (or the selected slot) and following free slots; "
                   "pick a slot outside the grid.")

    count: Count | None
    result_slot: Slot | None


class Equip(Tool):
    name = "equip"
    description = ("Swap the item in a robot inventory slot with the item in the robot tool slot "
                   "(e.g. to equip a pickaxe). The previous tool ends up in that slot.")

    slot: Slot


class Swing(Tool):
    name = "swing"
    description = ("Left-click with the equipped tool: break the block or attack the entity "
                   "on the given side (front/up/down only; turn to reach left/right/back). "
                   "One successful swing breaks a block; drops go to the robot inventory. "
                   "Hard blocks (stone, ores, furnaces) need a suitable tool equipped with equip, "
                   "otherwise the swing fails and says so.")

    side: Side = "front"
    sneaky: bool = False


class Place(Tool):
    name = "place"
    description = ("Place a block from a robot inventory slot on the given side "
                   "(front/up/down only; turn to reach left/right/back). "
                   "The target space must be free (air, water, tall grass); break it with swing first. "
                   "If slot is omitted, the currently selected slot is used. "
                   "sneaky places like a sneaking player (needed for some blocks).")

    side: Side = "front"
    slot: Slot | None
    sneaky: bool = False


class Use(Tool):
    name = "use"
    description = ("Right-click with the equipped tool on the given side: open/activate blocks, "
                   "place or use items, interact with entities. "
                   "duration is how many seconds to hold the click (e.g. for bows or eating).")

    side: Side = "front"
    sneaky: bool = False
    duration: Annotated[float, Range(0, 30)] | None


class Surroundings(Tool):
    name = "surroundings"
    description = ("Identify the six blocks right next to the robot, relative to where it faces now "
                   "(front, back, left, right, up, down; turning changes them): "
                   "block id, hardness, and for front/up/down whether it is solid, passable, liquid, "
                   "replaceable, air or an entity. Needs a geolyzer.")


Offset = Annotated[int, Range(-32, 32)]
Size = Annotated[int, Range(1, 64)]


class GeoScan(Tool):
    name = "geo_scan"
    description = ("Scan a box of blocks around the robot with the geolyzer and return their hardness "
                   "(not block names). Offsets are relative to the robot. With a navigation upgrade "
                   "the axes follow the robot: x = right, z = forward; without it they are world axes: "
                   "x = east, z = south. y = up. The first line of the answer states which axes were used. "
                   "width*depth*height must be <= 64. Values are noisy, more so farther away: "
                   ". = air, ~0.5 dirt/sand/gravel, ~1.5 stone, ~2-3 ores, ~50 obsidian, "
                   "100 liquid, -1 bedrock. Use surroundings to identify adjacent blocks exactly.")

    x: Offset = -4
    z: Offset = -4
    y: Offset = 0
    width: Size = 8
    depth: Size = 8
    height: Size = 1


class WorldInfo(Tool):
    name = "world_info"
    description = ("Identity and position of the robot for the memory service: world_id (configured on the "
                   "bridge, pass it to memory open as is), robot_id (address of the robot computer), "
                   "robot name, and with a navigation upgrade its x/y/z and facing.")

    @classmethod
    def context(cls, bridge):
        return {"world_id": bridge.world_id} if bridge.world_id else {}


Lang = str | None
Limit = Annotated[int, Range(1, 50)] | None

NEI_NOTE = (" Item ids are 'mod:name:damage' strings (e.g. minecraft:iron_ingot:0); get them with nei_find. "
            "Answers are JSON. Recipe data comes from a player's NEI client: "
            "NO_PROVIDER means no player with the mod is online.")


class NeiFind(Tool):
    name = "nei_find"
    description = ("Find items by name in any language. Supports @mod, #oreName, $unlocalized, /regex/; "
                   "terms are AND-ed. Returns item ids with names." + NEI_NOTE)
    timeout = 140

    text: str
    limit: Limit
    lang: Lang


class NeiRecipes(Tool):
    name = "nei_recipes"
    description = ("All recipes that produce the item (crafting table, furnace, machines), compact; "
                   "with usages=true, recipes that use the item as an ingredient instead. "
                   "Each recipe has an id for nei_recipe/nei_machine_plan; "
                   "category filters by part of the NEI category id or name (e.g. smelting, macerat). "
                   "If truncated, call again with the returned cursor." + NEI_NOTE)
    timeout = 60

    item: str
    usages: bool = False
    category: str | None
    limit: Limit
    cursor: str | None
    lang: Lang


class NeiRecipe(Tool):
    name = "nei_recipe"
    description = ("One recipe by id in full: every position with all interchangeable items, and for "
                   "crafting-table recipes the robot inventory slot (robotSlot) for each grid cell. "
                   "To craft it, pass the id to craft_recipe." + NEI_NOTE)
    timeout = 60

    recipe: str
    lang: Lang


class NeiCraftTree(Tool):
    name = "nei_craft_tree"
    description = ("Resolve the whole crafting tree of an item in one call: steps in execution order "
                   "(recipe id, category, runs, per-run in/out, robotSlot grid for crafting-table steps), "
                   "raw materials still to obtain, machines needed, alternatives. "
                   "use_inventory subtracts what the robot already carries. "
                   "Crafting-table steps: craft_recipe {recipe: step.recipe, count: step.runs}." + NEI_NOTE)
    timeout = 90

    item: str
    count: Annotated[int, Range(1, 1000000)] = 1
    use_inventory: bool = True
    lang: Lang


class CraftRecipe(Tool):
    name = "craft_recipe"
    description = ("Craft a crafting-table recipe by its NEI recipe id (from nei_recipes, nei_recipe or a "
                   "nei_craft_tree step). The robot moves whatever is in its crafting grid out of the way, "
                   "lays the ingredients out from its own inventory, crafts count times and puts the result "
                   "into a free slot outside the grid. Interchangeable ingredients (any planks, ore dictionary) "
                   "are matched automatically. Ingredients must already be in the robot inventory; "
                   "if something is missing, the answer lists it. Each grid slot holds at most 64 items, "
                   "so split bigger runs into several calls." + NEI_NOTE)
    timeout = 120

    recipe: str
    count: Count = 1


class NeiMachinePlan(Tool):
    name = "nei_machine_plan"
    description = ("For a machine/furnace next to the robot: which slots to put each ingredient of a recipe into "
                   "and where to take results, checked from the robot's position. "
                   "Use the put/take slots with storage_put/storage_take. "
                   "times = how many runs (step.runs from nei_craft_tree)." + NEI_NOTE)
    timeout = 60

    side: Side = "front"
    recipe: str
    times: Annotated[int, Range(1)] | None
    lang: Lang


TOOLS = [Move, Turn, InventoryScan, InventoryTransfer, StorageScan, StorageTake, StoragePut, Craft,
         Equip, Swing, Place, Use, Surroundings, GeoScan, WorldInfo,
         NeiFind, NeiRecipes, NeiRecipe, NeiCraftTree, CraftRecipe, NeiMachinePlan]
