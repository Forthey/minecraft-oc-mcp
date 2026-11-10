---
name: oc-design
description: Use when turning research notes into a build plan (spec.json and spec.md) for the OpenComputers robot, or when revising that plan after a failed stage or check. Used by the orchestrator itself, not by a subagent.
---

# OC design

There are no ready-made blueprints. You derive the build plan from research notes and write it as spec.json (machine-readable, validated by [spec-schema.json](../references/spec-schema.json)) and spec.md (the reasoning). Builders and verifiers work only from spec.json, so everything they need must be in it.

## Inputs

- Research notes in `research/`.
- task.md: goal, versions, warehouse position, `safety.require_confirm`.
- `get_status()` result: where the robot is and where there is free space.

## Rules

1. **Every block and slot has a source.** Each block, slot and acceptance check must follow from a fact in a research note. List the notes in `sources`. If a needed fact is missing or `low`, stop and order more research instead of guessing. Such a round counts against `design_revisions`. When that budget is used up, ask the user.
2. **Coordinates.** Pick `origin` in free space near the robot and the warehouse. Block positions are relative to `origin`.
3. **Placement order.** Bottom to top. Supporting blocks before what they hold. Inner blocks before outer ones, so the robot never walls itself out of a target.
4. **Stages.** Split the build into stages that can be checked on their own: structure, then slot contents (cooling, components), then dangerous steps, then activation. A stage should take at most about 30 placements. Stage ids are lowercase with dashes, numbered: `1-structure`, `2-cooling`.
5. **Gates.** A stage that inserts fuel gets `gate: insert_fuel`. A stage that turns a machine on gets `gate: activate_machine`. A stage that needs digging next to already placed blocks gets `gate: dig_near_structure`. Other stages get `gate: null`. The same applies to single checks: a check whose `actions` insert fuel or switch a machine on gets its own `gate` (for example the final check that flips the reactor lever gets `gate: activate_machine`). A check without such actions has no `gate` field.
6. **Acceptance checks.** `acceptance.structural: true` means the verifier runs `verify_blocks` on the stage blocks. Functional checks are objects with `description`, `actions` (the exact steps the verifier may perform, such as putting coal into a generator) and `expect` (an observable result). The verifier may change the world only through these actions, so write every needed action down.
7. **Safety.** For anything that can explode, burn, flood or break: write the risks into `safety`, order the stages so dangerous steps come last, and set `emergency_off` to the exact way to stop it at once. The schema requires `emergency_off` when a stage has gate `insert_fuel` or `activate_machine`. For harmless builds it is `null`.
8. **Final acceptance** proves the goal works, not only that blocks exist: energy produced, item processed, heat stable. It is never empty (the schema requires at least one check). For a plain structure, the final check is `verify_blocks` over the blocks of all stages.

## Minimal example (plain wall, no dangerous steps)

```json
{
  "goal": "3x3 cobblestone wall",
  "origin": [10, 64, 9],
  "stages": [
    {
      "id": "1-wall",
      "blocks": [
        {"pos": [0, 0, 0], "item": "minecraft:cobblestone"},
        {"pos": [1, 0, 0], "item": "minecraft:cobblestone"},
        {"pos": [2, 0, 0], "item": "minecraft:cobblestone"},
        {"pos": [0, 1, 0], "item": "minecraft:cobblestone"},
        {"pos": [1, 1, 0], "item": "minecraft:cobblestone"},
        {"pos": [2, 1, 0], "item": "minecraft:cobblestone"},
        {"pos": [0, 2, 0], "item": "minecraft:cobblestone"},
        {"pos": [1, 2, 0], "item": "minecraft:cobblestone"},
        {"pos": [2, 2, 0], "item": "minecraft:cobblestone"}
      ],
      "slots": [],
      "acceptance": {"structural": true, "functional": []},
      "gate": null
    }
  ],
  "safety": [],
  "final_acceptance": [
    {"description": "wall complete", "actions": ["verify_blocks on all blocks of stage 1-wall"], "expect": "missing and wrong are empty"}
  ],
  "emergency_off": null,
  "sources": []
}
```

A full example with slots, gates and `emergency_off` (IC2 reactor) is in [spec.example.json](../references/examples/spec.example.json).

## spec.md

Short, for the user and for you after a context reset:

- Goal and chosen layout in two or three sentences.
- Why this layout: the key facts, each with a link to its research note.
- Stage list with one line each.
- Risks and how `safety` and `emergency_off` handle them.
- Open questions or assumptions.

## Validation

After writing spec.json, check it against the schema if you can run code (for example with Python `jsonschema`). Otherwise go through the schema by hand: every stage has `id`, `blocks`, `slots`, `acceptance`, `gate`, and `emergency_off` is set when a gate needs it.

## Revising the spec

When a stage or check fails because the plan is wrong (not because of a robot error):

1. Check `design_revisions` in the journal. If the budget is used up, ask the user instead.
2. Write the reason into decisions.md and the failed layout into tried.md.
3. Change only the stages that must change. Stages before the earliest changed one keep their ids and their PASS. That stage and every stage after it are rebuilt and re-verified (the orchestrator invalidates them).
4. Increase the `design_revisions` counter in the next journal line.
