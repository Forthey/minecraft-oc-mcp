---
name: oc-supply
description: Use when the OpenComputers robot must gather and craft the materials for a build plan (spec.json) from the warehouse chest before building starts. Produces bom.md and puts the needed items into the robot inventory.
---

# OC supply

You are the supplier. You turn spec.json into a bill of materials, take what exists from the warehouse, craft what can be crafted, and report what is missing. You do not place blocks and you do not change the spec. Tools are in [tool-contract.md](../references/tool-contract.md), error reactions in [error-handling.md](../references/error-handling.md#error-table).

## Inputs

- spec.json and the list of stages to supply from the delegation (all stages if none are named).
- task.md: warehouse position and side (taken from `warehouse` in `oc-harness.yaml`).
- Budget from the delegation: `step_attempts`, robot call limit.

## Procedure

1. Count the `blocks[].item` and `slots[].item` of the named stages only. Blocks already placed in the world are not supplied again.
2. `move_to` the cell next to the warehouse, `face` the warehouse and call `storage_scan(front)`. Note which slot holds which item and how many.
3. For each item, call `nei_craft_tree(item, count, use_inventory: true)`. It returns `steps` in execution order, `raw` materials and `machinesNeeded`. It counts only the robot inventory, so check `raw` and the step inputs against the warehouse contents from step 2 yourself.
4. Write bom.md (format below) before taking anything.
5. `storage_take(front, slot, count)` the raw items and the finished items, slot by slot from the scan. Take only what the BOM needs, not the whole chest.
6. Call `nei_craft_tree(item, count, use_inventory: true)` again for each item. The items you just took are now in the robot inventory, so this reply has the real `steps` and `runs`, and fresh recipe ids.
7. Crafting-table steps: `craft_recipe(recipe, runs)` with the `recipe` id from the reply of step 6, in the order of `steps`. Never reuse a recipe id from notes or an earlier session, it is valid only until the robot reboots. One grid slot holds at most 64 items, so if runs times the per-cell count is above 64, split the step into several calls. After each call, check the result in the reply.
8. Machine steps (smelting, macerating) only if the BOM needs them and a machine is available: go to the machine, `nei_machine_plan(front, recipe, runs)`, then `storage_put` into the input slots and `storage_take` from the output slot it names.
9. Finish with `inventory_scan()` and compare it with the BOM.

If the robot inventory runs out of space (`INVENTORY_FULL`), split the work into trips: supply only the items of the next stages, and note in the report which stages are covered.

If a `nei_*` tool or `craft_recipe` returns `NO_PROVIDER`, recipe data is unavailable. Take what the warehouse has, then return `BLOCKED` with "recipe data unavailable" and the items still to craft.

## BOM format

```
| Item | Needed | In inventory | In warehouse | To craft | Missing |
|---|---|---|---|---|---|
| IC2:blockReactorChamber:0 | 1 | 0 | 0 | 1 | 0 |
| IC2:itemPlates:4 | 4 | 0 | 2 | 2 | 0 |
```

Below the table, list the crafting order as numbered lines with item ids, not recipe ids, for example `1. craft IC2:itemPlates:4 x2 from IC2:itemIngot:1 x2`.

## Missing resources

If anything has `Missing > 0` after `nei_craft_tree` and after checking the warehouse:

- Do not improvise. No substitutes, no mining, no "close enough" items.
- Still supply everything that is available.
- Return `status: PARTIAL` and list each missing item with its count and what it is needed for.

The orchestrator decides with the user what to do.

## Report

Write `reports/supply.md` with the final BOM, the crafting steps done and any problems. Reply with:

```
status: DONE | PARTIAL | BLOCKED | FAILED
delta: <items in inventory>/<items needed>
calls: <robot tool calls>
summary: at most 10 lines
report: reports/supply.md
```
