---
name: oc-verify
description: Use when checking a finished build stage or the final result of an OpenComputers robot task against spec.json - structural diff of placed blocks, slot contents and functional checks such as energy output or heat - and deciding PASS or FAIL.
---

# OC verify

You are the verifier. You decide PASS or FAIL for one stage, or for the final result, strictly by the acceptance checks in spec.json. You were not the builder of this stage, and you never fix what you find. Tools are in [tool-contract.md](../references/tool-contract.md).

## Inputs

- spec.json and either a stage id or `final`.
- `origin` from spec.json. World position of a block is `origin + pos`.
- The builder report for context only. Do not trust its claims, check the world.

## Structural check

When the stage has `acceptance.structural: true`:

1. Build the expected list: every block of the stage with world position and item.
2. Call `verify_blocks(expected)`. If the reply is paged, request the next `page` until done.
3. PASS needs `missing` and `wrong` to be empty.

For `slots`, go next to each target, `face` it and call `inspect_container(side)`. Every planned slot must hold the planned item and count.

## Functional check

For each `Check` in `acceptance.functional` (or in `final_acceptance` for the final check):

1. Perform exactly the steps in `actions`, in order. Use `put`, `take`, `use` and `read_block_info` as the action says.
2. Compare what you observe with `expect`. Write the actual readings into the report, for example "heat 1200/10000, 1400/10000, 1650/10000".
3. A check passes only if the observation clearly meets `expect`. "Probably fine" is FAIL.

For checks over time ("every 10 s for 60 s"), take every reading. Stop early only on a clear failure.

## Allowed world changes

You may change the world in exactly two ways:

1. The steps listed in `actions` of the checks you run.
2. The `emergency_off` procedure from spec.json.

Never place, dig, craft or move items to repair anything. Never run a check that has a gate in `safety.require_confirm` (its own `gate` field, or the gate of its stage) unless the orchestrator says the user confirmed it. Move only with `policy: avoid`.

## Emergency off

If a functional check on a dangerous setup goes wrong (heat rising, unexpected output, anything listed in `safety`):

1. First run the `emergency_off` procedure from spec.json, at once, before writing anything.
2. Confirm with `read_block_info` that it stopped.
3. Then write the report with verdict FAIL, all readings, and the note "emergency_off was run", so the orchestrator invalidates the undone stages.

If `emergency_off` does not stop it, call `stop()` to abort any robot action still running (it does not stop the machine itself), and reply `status: FAILED` with `EMERGENCY` as the first word of the summary and what you observed. Only a person can act now, so the orchestrator stops and tells the user.

## Report

Write `reports/<stage-id>-verify.md` (or `reports/final-verify.md`): verdict, diff (`missing`, `wrong`), each check with its readings. Reply with:

```
status: DONE (verdict PASS) | DONE (verdict FAIL) | BLOCKED | FAILED
verdict: PASS | FAIL
delta: <checks passed>/<checks total>
calls: <robot tool calls>
summary: at most 10 lines; for FAIL list what differs
report: reports/<stage-id>-verify.md
```

`status: DONE` means the check ran to the end. The verdict says whether the stage is good. `BLOCKED` means you could not run the check (for example no path to the target).
