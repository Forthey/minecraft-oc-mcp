# Robot MCP tool contract (draft)

This file is the single source of tool names for the skills. If the real MCP server differs, change this file.

The team keeps a Russian copy with examples and open questions in `docs/mcp-contract.md` (repository root, not installed with the skills). When you change a tool, a parameter or an error code here, make the same change there in the same edit, then run the tests: `test_team_contract_doc_in_sync` fails if the two files list different tools or error codes.

Items marked `(assumption, confirm with team)` are guesses about what the robot side can do. Treat them as available, but if a call returns an error that says the tool does not exist, report it as `BLOCKED` with that fact instead of working around it.

## Principles

1. **Absolute coordinates.** Positions are `[x, y, z]` world coordinates. The robot's heading is `facing`, one of `north | south | east | west`. A `side` argument is one of `front | up | down`, plus `back | left | right` when the tool turns the robot by itself.
2. **One response shape.** Every tool returns `{ok, error_code?, message, data}`. When `ok` is false, `error_code` is one of the codes in [Error codes](#error-codes).
3. **Compact by default.** Large results (scans, inventories, recipe trees, diffs) come back as a summary. Ask for details explicitly with `detail`, `limit` and `page`. Never request full detail just to look around.
4. **High-level actions first.** Prefer `move_to` and `place_at` over chains of `move` and `place`.

## Tools

### State

| Tool | Purpose |
|---|---|
| `get_status()` | Position, facing, energy, tool durability, inventory summary (used slots, top items), warehouse position |
| `inspect(side)` | Name and metadata of the adjacent block on `side` |
| `scan_area(box, detail)` | Summary of a region: air, solid, liquid, known blocks. Far blocks have no exact ids (geolyzer limits, assumption, confirm with team). `box` is `{from: [x,y,z], to: [x,y,z]}`, `detail` is `summary | full` |
| `get_known_map(box)` | What the robot already remembers about a region, without scanning |

### Movement

| Tool | Purpose |
|---|---|
| `move_to(x, y, z, policy)` | Pathfinding move. `policy` is `avoid` (never break blocks) or `dig_through` (break blocks in the way) |
| `move(dir, n)` | Low-level move `n` blocks in `dir` (`forward | back | up | down`). Fallback only |
| `face(dir)` | Turn to `north | south | east | west` |

### World

| Tool | Purpose |
|---|---|
| `dig(side)` | Break the block on `side` |
| `place(item, side)` | Place `item` from inventory on `side` |
| `place_at(x, y, z, item, from?)` | Move next to the target and place `item` there. `from` optionally sets the side to approach from |
| `use(side, item?)` | Right-click the block on `side`, optionally holding `item` |

### Inventory

| Tool | Purpose |
|---|---|
| `list_inventory(detail)` | Robot inventory. `detail` is `summary | full` |
| `inspect_container(side)` | Contents of the chest or machine on `side`, slot by slot |
| `take(side, item, count, slot?)` | Take items from the container on `side` |
| `put(side, item, count, slot?)` | Put items into the container on `side`, optionally into a specific machine slot |
| `equip(item)` | Equip a tool |
| `drop(item, count)` | Drop items in front of the robot |

### Crafting

| Tool | Purpose |
|---|---|
| `craft(item, count)` | Craft with the crafting upgrade. The tool arranges the 3x3 grid by itself |

Machine processing (furnace, macerator and so on) has no dedicated tool: use `put` into the input slot, wait, then `take` from the output slot.

### Knowledge

| Tool | Purpose |
|---|---|
| `search_items(query, limit)` | Search the item index (RAG) |
| `get_item(id)` | Item card: name, id, mod, short description |
| `get_recipes(item)` | Crafting table and machine recipes (NEI dump) |
| `plan_materials(item, count, use_inventory)` | Crafting tree and what is still missing, counting the robot inventory and the warehouse when `use_inventory` is true |
| `search_docs(query, mod?, limit)` | Search mod documentation about mechanics, multiblocks and machine setup (RAG) |

### Verification

| Tool | Purpose |
|---|---|
| `verify_blocks(expected, page?)` | Compare a list `[{pos, item}]` with the world. Returns a compact diff `missing / wrong`. Uses `inspect` in a normal world and a debug card in tests (assumption, confirm with team) |
| `read_block_info(side)` | State of the machine on `side`: energy, heat, active flag, slots (assumption, confirm with team: depends on OpenComputers drivers for IC2) |

### Service

| Tool | Purpose |
|---|---|
| `stop()` | Abort the current robot action |
| `get_action_log(last_n)` | Last `last_n` robot actions with results |

## Error codes

| Code | Meaning |
|---|---|
| `BLOCKED` | Something occupies the target or the way, and the action cannot proceed |
| `NO_PATH` | Pathfinding found no route with the given policy |
| `OUT_OF_RANGE` | Target is too far or outside the loaded or allowed area |
| `NO_ITEM` | The required item is not in the robot inventory or the container |
| `INVENTORY_FULL` | No free slot to receive items |
| `NO_ENERGY` | Robot energy is too low for the action |
| `TOOL_BROKEN` | Equipped tool is broken or missing |
| `CANT_PLACE` | The block cannot be placed there (no support, wrong side, protected area) |
| `UNKNOWN_ITEM` | Item id or name not recognized |
| `NO_RECIPE` | No known recipe for the item |
| `TIMEOUT` | The action did not finish in time |
| `CONNECTION_LOST` | The link to the robot dropped. The action may or may not have happened |
