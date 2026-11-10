from typing import Annotated, Literal, Optional

from schema import Range, Tool

Side = Literal["front", "up", "down"]
Slot = Annotated[int, Range(1)]
Count = Annotated[int, Range(1, 64)]


class Print(Tool):
    name = "print"
    description = "Print a string on the OpenComputers robot screen."

    message: str


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
    count: Optional[Count]


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
    count: Optional[Count]
    robot_slot: Optional[Slot]


class StoragePut(Tool):
    name = "storage_put"
    description = ("Put items from a robot slot into an adjacent storage. "
                   "If slot is omitted, the storage picks the slot itself.")

    side: Side
    robot_slot: Slot
    count: Optional[Count]
    slot: Optional[Slot]


class Craft(Tool):
    name = "craft"
    description = ("Craft using the robot inventory as a 3x3 crafting grid. "
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

    count: Optional[Count]
    result_slot: Optional[Slot]


class Equip(Tool):
    name = "equip"
    description = ("Swap the item in a robot inventory slot with the item in the robot tool slot "
                   "(e.g. to equip a pickaxe). The previous tool ends up in that slot.")

    slot: Slot


class Swing(Tool):
    name = "swing"
    description = ("Left-click with the equipped tool: break the block or attack the entity "
                   "on the given side. Dropped items go to the robot inventory. "
                   "Reports what was hit and the remaining tool durability.")

    side: Side = "front"
    sneaky: bool = False


class Use(Tool):
    name = "use"
    description = ("Right-click with the equipped tool on the given side: open/activate blocks, "
                   "place or use items, interact with entities. "
                   "duration is how many seconds to hold the click (e.g. for bows or eating).")

    side: Side = "front"
    sneaky: bool = False
    duration: Optional[Annotated[float, Range(0, 30)]]


TOOLS = [Print, Move, Turn, InventoryScan, InventoryTransfer, StorageScan, StorageTake, StoragePut, Craft,
         Equip, Swing, Use]
