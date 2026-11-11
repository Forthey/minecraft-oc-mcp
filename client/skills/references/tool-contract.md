# Robot MCP tool contract (v2)

This file is the single source of tool names for the skills. If the real MCP server differs, change this file.

The team keeps a Russian copy with examples and open questions in `docs/mcp-contract.md` (repository root, not installed with the skills). When you change a tool, a parameter or an error code here, make the same change there in the same edit, and in the stand fake MCP (`stand/fake_mcp/dispatch.py`), then run the tests: `test_team_contract_doc_in_sync` fails if the two files list different tools or error codes, `test_tool_specs_match_contract` fails if the fake MCP differs.

Most tools come from `oc-mcp`, the team's MCP server for the robot. They are marked `oc-mcp`. Tools marked `addition` are high-level tools that our adapter builds on top of them.

## Principles

1. **Two levels.** `oc-mcp` tools work relative to the robot: a `side` is `front | up | down`, robot slots are numbered from 1, the crafting grid is robot slots `1,2,3 / 5,6,7 / 9,10,11`. Additions work in world coordinates `[x, y, z]` and with absolute directions `north | south | east | west`. You can mix both levels.
2. **High-level actions first.** Prefer `move_to`, `place_at` and `verify_blocks` over chains of `move`, `turn` and `place`. Use the low-level tools only as a fallback, for example after `NO_PATH`.
3. **Item ids.** Ids have the NEI form `mod:name:damage`, for example `minecraft:cobblestone:0`, `IC2:blockMachine:3`. Additions also accept `mod:name`, which means damage 0.
4. **One response shape.** Every tool returns `{ok, error_code?, message, data}`. For `oc-mcp` tools `message` is the robot's text as is. `data` is always an object: `nei_*` and `world_info` put their JSON there, `inventory_scan` and `storage_scan` put `{"slots": [{slot, count, name, label}]}` there. When `ok` is false, `error_code` is one of the codes in [Error codes](#error-codes).
5. **Recipe ids are short-lived.** A recipe id such as `r7fbebd0471463308` is valid only until the robot reboots. Keep item ids in notes and plans, get recipe ids again from `nei_recipes` or `nei_craft_tree` right before you use them.

## Tools

### State

| Tool | Purpose |
|---|---|
| `get_status()` | Position, facing and inventory slots: `{pos, facing, inventory: [{slot, count, name}]}` (addition) |
| `world_info()` | Robot id and name, world id, position and facing (oc-mcp) |
| `surroundings()` | The six blocks next to the robot, relative to its facing: block id and kind (oc-mcp) |
| `geo_scan(x, z, y, width, depth, height)` | Hardness of a box around the robot, axes x = right, z = forward, y = up. No block names. `width*depth*height <= 64` (oc-mcp) |

### Movement

| Tool | Purpose |
|---|---|
| `move_to(x, y, z, policy)` | Pathfinding move to a world position. `policy` is `avoid` (never break blocks) or `dig_through` (break blocks in the way). Data `{pos, steps, dug}` (addition) |
| `face(direction)` | Turn to `north | south | east | west` (addition) |
| `move(direction, n)` | Move `n` blocks `forward | back | up | down`, stops at the first obstacle (oc-mcp) |
| `turn(direction)` | Turn `left | right | around` (oc-mcp) |

### World

| Tool | Purpose |
|---|---|
| `place_at(x, y, z, item, from)` | Move next to the target and place `item` there. Finds the slot by itself. `from` optionally sets the side to approach from. Data `{pos, slot}` (addition) |
| `place(side, slot, sneaky)` | Place the block from a robot slot on `side` (oc-mcp) |
| `swing(side, sneaky)` | Break the block on `side` with the equipped tool, drops go to the inventory (oc-mcp) |
| `use(side, sneaky, duration)` | Right-click on `side` with the equipped tool (oc-mcp) |

### Inventory

| Tool | Purpose |
|---|---|
| `inventory_scan()` | Non-empty robot slots (oc-mcp) |
| `inventory_transfer(from_slot, to_slot, count)` | Move items between robot slots. A slot with another item is refused (oc-mcp) |
| `storage_scan(side)` | Non-empty slots of the chest or machine on `side` and its block id (oc-mcp) |
| `storage_take(side, slot, count, robot_slot)` | Take items from a slot of the storage on `side` (oc-mcp) |
| `storage_put(side, robot_slot, count, slot)` | Put items from a robot slot into the storage on `side`, optionally into a given storage slot (oc-mcp) |
| `equip(slot)` | Swap a robot slot with the tool slot (oc-mcp) |

### Crafting

| Tool | Purpose |
|---|---|
| `craft_recipe(recipe, count)` | Craft a crafting-table recipe by its NEI recipe id. Lays out the grid from the robot inventory, the result goes outside the grid (oc-mcp) |
| `craft(count, result_slot)` | Low-level: craft whatever is laid out in the grid slots `1,2,3 / 5,6,7 / 9,10,11` (oc-mcp) |

### Knowledge

| Tool | Purpose |
|---|---|
| `nei_find(text, limit, lang)` | Find items by name, returns item ids with labels (oc-mcp) |
| `nei_recipes(item, usages, category, limit, cursor, lang)` | All recipes that make the item, or with `usages` the recipes that use it. Each has an id (oc-mcp) |
| `nei_recipe(recipe, lang)` | One recipe in full, with the robot slot for every grid cell (oc-mcp) |
| `nei_craft_tree(item, count, use_inventory, lang)` | The whole crafting tree: `steps` in execution order with recipe ids and runs, `raw` materials still needed, `machinesNeeded`. Counts only the robot inventory, not the warehouse (oc-mcp) |
| `nei_machine_plan(side, recipe, times, lang)` | For the machine on `side`: which slots to put each ingredient into and where to take the result (oc-mcp) |
| `search_docs(query, mod, limit)` | Search mod documentation about mechanics, multiblocks and machine setup. May be `UNSUPPORTED` until the RAG service exists (addition) |

### Verification

| Tool | Purpose |
|---|---|
| `verify_blocks(expected, page)` | Compare a list `[{pos, item}]` with the world. Returns `{checked, missing, wrong, next_page}`, 50 entries per page (addition) |

### Service

| Tool | Purpose |
|---|---|
| `get_action_log(last_n)` | Last `last_n` robot actions with results (addition) |

## Error codes

| Code | Meaning |
|---|---|
| `BLOCKED` | Something occupies the target or the way, and the action cannot proceed |
| `NO_PATH` | Pathfinding found no route with the given policy |
| `OUT_OF_RANGE` | Target is too far or outside the loaded or allowed area |
| `NO_ITEM` | The required item is not in the robot inventory or the container, or the slot is empty |
| `INVENTORY_FULL` | No free slot to receive items |
| `NO_ENERGY` | Robot energy is too low for the action |
| `TOOL_BROKEN` | The equipped tool is missing, broken or cannot break this block |
| `CANT_PLACE` | The block cannot be placed there (no support, occupied target, item is not a block) |
| `UNKNOWN_ITEM` | Item id or name not recognized |
| `NO_RECIPE` | No known recipe for the item, the recipe id is unknown or it is not a crafting-table recipe |
| `TIMEOUT` | The action did not finish in time |
| `CONNECTION_LOST` | The link to the robot dropped. The action may or may not have happened |
| `UNSUPPORTED` | The robot lacks the component or upgrade this tool needs. The message names it |
| `NO_PROVIDER` | Recipe data is unavailable right now: no player with NEI is online and the answer is not cached |
| `UNKNOWN` | The error text was not recognized. Treat it as `BLOCKED` |
