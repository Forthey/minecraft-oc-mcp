---
name: oc-supply
description: Use when the OpenComputers robot must gather and craft the materials for a build plan (spec.json) from the warehouse chest before building starts. Produces bom.md and puts the needed items into the robot inventory.
---

# OC supply

You are the supplier. You turn spec.json into a bill of materials, take what exists from the warehouse, craft what can be crafted, and report what is missing. You do not place blocks and you do not change the spec. Tools are in [tool-contract.md](../references/tool-contract.md), error reactions in [error-handling.md](../references/error-handling.md#error-table).

## Inputs

- spec.json and the list of stages to supply from the delegation (all stages if none are named).
- task.md: warehouse position and side.
- Budget from the delegation: `step_attempts`, robot call limit.

## Procedure

1. Count the `blocks[].item` and `slots[].item` of the named stages only. Blocks already placed in the world are not supplied again.
2. For each item, call `plan_materials(item, count, use_inventory: true)`. It returns the crafting tree and what is still missing, counting the robot inventory and the warehouse.
3. Write bom.md (format below) before moving the robot.
4. `move_to` the warehouse, `face` its side, check it with `inspect_container`.
5. `take` the raw items and the finished items. Take only what the BOM needs, not the whole chest.
6. `craft` intermediate items first, following the tree from leaves to root. After each `craft`, check the result count in the reply.
7. Machine steps (smelting, macerating) go through `put` into the machine input slot and `take` from the output slot, if the BOM needs them and a machine is available.
8. Finish with `list_inventory(detail: summary)` and compare it with the BOM.

If the robot inventory runs out of space (`INVENTORY_FULL`), split the work into trips: supply only the items of the next stages, and note in the report which stages are covered.

## BOM format

```
| Item | Needed | In inventory | In warehouse | To craft | Missing |
|---|---|---|---|---|---|
| IC2:blockReactorChamber | 1 | 0 | 0 | 1 | 0 |
| IC2:itemPlates:4 | 4 | 0 | 2 | 2 | 0 |
```

Below the table, list the crafting order as numbered lines, for example `1. craft IC2:itemPlates:4 x2 from IC2:itemIngot:1 x2`.

## Missing resources

If anything has `Missing > 0` after `plan_materials` and after checking the warehouse:

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
