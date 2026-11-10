# Error handling and anti-loop rules

Every role follows this file. Budget names refer to keys in [config.md](config.md).

## Error table

"First" is the reaction to the first failure of a step, "Second" to the second failure of the same step. "Then" applies when the second reaction also fails. Never send the same call a third time.

| Code | First | Second | Then |
|---|---|---|---|
| `BLOCKED` | `inspect` the side to learn what is there | Change approach: other side, other approach position, or reorder placement if your own block is in the way | Return `BLOCKED` with what you saw |
| `NO_PATH` | Pick another approach position next to the target, still with `policy: avoid` | Retry `move_to` with `policy: dig_through` only if no placed structure block, warehouse or machine is near the path, or the stage has gate `dig_near_structure`. Otherwise skip this reaction | Return `BLOCKED` with a hypothesis, for example "target enclosed by own blocks" |
| `OUT_OF_RANGE` | `get_status` and check the target coordinates for a typo or wrong origin | none | Return `BLOCKED` |
| `NO_ITEM` | `list_inventory` to confirm | Builder and verifier: return `BLOCKED`, supply is not your job. Supplier: check the warehouse with `inspect_container` | Return `PARTIAL` with the missing items |
| `INVENTORY_FULL` | Supplier: split the transfer into several trips. Builder: `put` unused items back into the warehouse | none | Return `BLOCKED` |
| `NO_ENERGY` | Stop all actions | none | Return `BLOCKED`. The orchestrator asks the user to charge the robot |
| `TOOL_BROKEN` | `equip` a spare tool if the inventory has one | none | Return `BLOCKED` with the tool name |
| `CANT_PLACE` | `inspect` the target and its neighbors, check that a support block exists | Place the supporting block first if it is in the spec, otherwise change the approach side | Return `BLOCKED` |
| `UNKNOWN_ITEM` | `search_items` for the right id | Use the id from the search result once | Return `FAILED`: the spec or BOM has a wrong id |
| `NO_RECIPE` | `get_recipes` with an alternative name from `search_items` | none | Return `PARTIAL`. The orchestrator treats the item as missing |
| `TIMEOUT` | `get_status` to see whether the action happened | Repeat once only if the state shows it did not happen | Return `BLOCKED` |
| `CONNECTION_LOST` | Do not repeat the action. Call `get_status` and compare position and inventory with the journal and your last report | Continue from the real state, not from the assumed one | If `get_status` keeps failing, return `BLOCKED` |

## Anti-loop rules

1. **No third identical call.** The same tool with the same arguments and the same error is never called a third time. After the second failure, change the approach or return `BLOCKED`.
2. **Read tried.md first.** Before choosing a new approach, read tried.md. Never repeat an approach recorded there as failed. Append every failed approach to tried.md as `- <stage>: <approach> -> <error or result>`.
3. **Progress must be measurable.** Every subagent report has a delta (blocks placed, items crafted, questions answered). Two reports in a row for the same stage with zero delta mean escalation, even if the budget is not used up.
4. **Budgets are counted, not felt.** Count attempts and calls explicitly and put them into your reply (`delta`, `calls`). Only the orchestrator writes status lines to journal.md, from these replies. Subagents append only to tried.md.
5. **The table sets the order, `step_attempts` sets the cap.** Follow the First, Second, Then columns in order. If a row says to return early (for example after the Second reaction), do so even if `step_attempts` is not used up. Never go beyond `step_attempts` for one step.

## Escalation ladder

Each rung has its own budget. Move to the next rung only when the current one is exhausted.

1. **Local variation** inside the subagent. Budget: `step_attempts` per step, `robot_calls_per_stage` per stage.
2. **`BLOCKED` to the orchestrator** with a hypothesis and the attempts made.
3. **Re-plan the stage.** The orchestrator changes order, approach positions or stage split and re-delegates. Budget: `stage_redelegations`.
4. **Revise the spec or research more.** Budget: `design_revisions`.
5. **Ask the user.** Explain what was tried (from tried.md), what is known, and offer concrete options.
