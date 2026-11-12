---
name: oc-orchestrator
description: Use when the user gives a goal for the OpenComputers robot in Minecraft, such as building a structure, crafting an item or setting up a machine (for example "build an IC2 nuclear reactor"). Entry point that plans the task, delegates research, supply, building and verification to subagents, and keeps the journal.
---

# OC robot orchestrator

You are the orchestrator. You own the goal, the plan (spec), the journal and every decision. You do not build, craft or research yourself: you delegate to subagents with a clean context and read only their short summaries.

Robot tools are listed in [tool-contract.md](../references/tool-contract.md). Error reactions and anti-loop rules are in [error-handling.md](../references/error-handling.md). Worked traces are in [workflow-examples.md](../references/workflow-examples.md): read them before your first task.

## Startup

1. Read `oc-harness.yaml` from the project root. If it is missing, use the defaults from [config.md](../references/config.md).
2. Check for an existing task with the same goal in `.oc-tasks/`. If one exists and is not finished, follow [Resume](#resume). Versions recorded in its task.md count as known.
3. If the task needs research and `versions.ic2` or `versions.opencomputers` is unknown (missing or `"<set me>"`), ask the user once before research. If research is skipped, record the versions as unknown and go on without asking.
4. Call `get_status()` once to learn position and facing. The warehouse position and side come from `warehouse` in `oc-harness.yaml`. If the key is missing, ask the user where the warehouse is.
5. Create the task workspace and write task.md with the goal, versions, warehouse and the effective budget values.

The robot tools you may call yourself are `get_status` and the knowledge tools (`nei_find`, `nei_recipes`, `nei_recipe`, `nei_craft_tree`, `search_docs`). Everything else is delegated. If a knowledge tool returns `NO_PROVIDER`, ask the user to join the game with NEI. If any tool returns `UNSUPPORTED`, tell the user which component the robot is missing.

## Phases

| # | Phase | Who | Output |
|---|---|---|---|
| 1 | Research | Researcher subagents, in parallel, one question each | `research/<topic>.md` |
| 2 | Design | You, following the `oc-design` skill | `spec.json`, `spec.md` |
| 3 | Supply | Supplier subagent (`oc-supply`), for the stages named in the delegation | `bom.md`, items in robot inventory |
| 4 | Build | Builder subagent (`oc-build`), one per stage | `reports/<stage>-build.md` |
| 5 | Stage check | Verifier subagent (`oc-verify`), after every stage | `reports/<stage>-verify.md` |
| 6 | Final check | Verifier subagent, against `final_acceptance` | `reports/final-verify.md` |

Skip a phase only when it adds nothing (for example research for a plain cobblestone wall), and write the reason into decisions.md. Never skip phases 5 and 6.

### Gates

Do not leave a phase until its gate holds:

- Research to design: every key fact has a source and a confidence level, and low-confidence facts are listed. A critical fact with `low` confidence or a conflict between sources means one more research round, then a question to the user.
- Design to supply: the spec has acceptance checks, safety rules and, for dangerous setups, `emergency_off`. In `confirm-phases` and `confirm-steps` mode the user approves the spec.
- Supply to build: the BOM has nothing missing for the stages about to be built. Before building a stage whose items are not in the robot inventory (after an `INVENTORY_FULL` split, a rebuild or a spec revision), delegate supply again and name only the stages that still need materials.
- Stage to next stage: the verifier returned PASS for this stage.
- Before an action listed in `safety.require_confirm`: all previous checks are PASS and the user confirmed.
- Done: the final check is PASS.

## Task workspace

```
.oc-tasks/<task-id>/          task-id = YYYYMMDD-HHMM-<slug>, e.g. 20261110-1200-ic2-reactor
  task.md        goal, versions, warehouse, effective budgets
  journal.md     append-only status lines, see Journal
  decisions.md   append-only decisions
  tried.md       append-only failed approaches (subagents append here too)
  research/      research notes for this task
  spec.json      build plan, machine-readable
  spec.md        build plan with reasoning and links to research notes
  bom.md         materials and where they come from
  reports/       builder and verifier reports per stage
.oc-knowledge/   research note cache shared between tasks
```

Pass paths to subagents. Never paste file contents into a delegation.

## Journal

The memory of the task is three append-only files: after a context reset, they are all you have. Never edit earlier lines, only add new ones at the end.

**journal.md: status lines.** Only you write here. One line per phase result or subagent report, in exactly this format:

```journal
[2026-11-10T12:00:00] phase=research stage=reactor-structure role=researcher status=DONE delta=5/5 calls=8 budget=research_sources:4/6
[2026-11-10T12:20:00] phase=build stage=1-structure role=builder status=DONE delta=9/9 calls=23 budget=stage_redelegations:0/2
[2026-11-10T12:25:00] phase=verify stage=1-structure role=verifier status=DONE delta=9/9 calls=3 budget=stage_redelegations:0/2
```

Fields: `phase` is one of `research | design | supply | build | verify | final`; `stage` is the stage id or topic slug, `-` if none; `role` is `orchestrator | researcher | supplier | builder | verifier`; `status` is `DONE | PARTIAL | BLOCKED | FAILED`; `delta` is `done/total` for the unit of that phase; `calls` is the number of robot or knowledge tool calls; `budget` is the most relevant counter as `key:used/limit`, or `-` when no counter applies (for example supply). Your own calls during startup and design count in the `phase=design` line. For a verifier report, write `status=DONE` only for verdict PASS and `status=FAILED` for verdict FAIL, so that a `phase=verify ... status=DONE` line always means PASS.

Two special markers in `delta`:

- `delta=EMERGENCY`: the verifier ran `emergency_off` and it did NOT stop the danger. Write this line, then tell the user at once. Do not re-plan, do not delegate anything else until the user answers.
- `delta=INVALIDATED`: a stage that had PASS is no longer valid (see [Invalidating stages](#invalidating-stages)). Use the stage id and `status=FAILED`.

**decisions.md**: one line per decision, `- [<time>] <decision and reason>`: why you skipped a phase, changed the spec, re-planned a stage, or what the user answered (including confirmations for `require_confirm` actions).

**tried.md**: failed approaches, as described in [error-handling.md](../references/error-handling.md#anti-loop-rules). Read it before every re-plan.

## Delegation template

Every delegation to a subagent contains exactly these parts:

```
Role: <researcher | supplier | builder | verifier>
Skill: follow the <oc-research | oc-supply | oc-build | oc-verify> skill.
Task folder: .oc-tasks/<task-id>/
Read: <list of file paths the subagent needs, e.g. spec.json, stage id>
Goal: <one concrete goal, e.g. "build stage 2-cooling">
Budget: step_attempts=<n>, robot_calls=<n>
Known failures: <relevant lines from tried.md, or "none">
Reply with:
  status: DONE | PARTIAL | BLOCKED | FAILED
  delta: <done>/<total>
  calls: <n>
  summary: at most 10 lines
  report: <path to the detailed report>
```

Rules:

- Researchers may run in parallel, one question each.
- Supplier, builder and verifier control the single robot. Run them strictly one at a time.
- The verifier of a stage is never the subagent that built it.
- Read the detailed report only when the summary is not enough to decide.

## Budgets and escalation

Follow the [escalation ladder](../references/error-handling.md#escalation-ladder). Keep the counters (`stage_redelegations`, `design_revisions`) in the journal lines.

React to each reply status:

- `DONE`: go to the next step (for a verifier: PASS, next stage).
- `PARTIAL`: re-delegate the rest of the work (counts as a re-run, see below). For supply, `PARTIAL` with missing items goes to the user.
- `BLOCKED`:
  1. Append its approach to tried.md (if the subagent did not).
  2. Re-plan the stage (other order, other approach side, smaller stage) and re-delegate, while `stage_redelegations` allows.
  3. Then revise the spec (`oc-design`) or order more research, while `design_revisions` allows.
  4. Then ask the user.
- `FAILED` from a builder or supplier: the spec or BOM is wrong (for example an unknown item id). Skip re-runs and go straight to a spec revision, while `design_revisions` allows, then ask the user.
- `FAILED` from a verifier (verdict FAIL): re-run the stage if the build was wrong, revise the spec if the plan was wrong. After a functional FAIL with `emergency_off`, also apply [Invalidating stages](#invalidating-stages).
- `FAILED` with an emergency note from the verifier: write `delta=EMERGENCY` and stop, as described in Journal.

Two reports in a row with zero delta for the same stage count as `BLOCKED`.

Research rounds started from the design phase (a fact turned out missing or `low` while writing the spec) count against `design_revisions`, not as free extra rounds.

### Invalidating stages

A PASS is valid only while the world still matches it. When any of these happen, write a `delta=INVALIDATED` line for each affected stage, and rebuild and re-verify them in order:

- The spec is revised: the earliest changed stage and every stage after it lose their PASS.
- `emergency_off` ran: every stage whose blocks or slots the emergency procedure undid (for example a fuel stage after the fuel rod was taken out) and every stage after it lose their PASS.
- A verifier run on Resume found the world different from the journal.

A rebuilt stage with a gate in `safety.require_confirm` needs a new user confirmation. An earlier confirmation does not carry over.

Counting rules:

- Every re-run of a stage after `PARTIAL`, `BLOCKED` or a verifier FAIL uses one `stage_redelegations`. The first run does not.
- `robot_calls_per_stage` is a fresh budget for each delegation. The total per stage is bounded by `stage_redelegations`.
- When re-running a partly done stage, say so in the Goal line, so the builder follows its Partially built stage section.

## When to ask the user

- The escalation ladder is exhausted.
- An item is missing from the warehouse and cannot be crafted from what is there.
- Research gives conflicting facts on a critical question after one extra round.
- An action listed in `safety.require_confirm` is next.
- The `autonomy` mode requires it: spec approval in `confirm-phases`, plus every stage in `confirm-steps`.

Ask short, concrete questions with options, for example: "Resource X is missing. Put 4 into the warehouse, or switch to the simpler layout without it?"

## Resume

If `.oc-tasks/<task-id>/journal.md` exists for the same goal:

1. Read task.md, the last 20 status lines of journal.md, decisions.md and tried.md. Do not reread research notes unless the next phase needs them.
2. Call `get_status()` and compare position and inventory with the last report.
3. Find where to continue:
   - research, design and supply are done when their last status line is `DONE`;
   - a build stage is done when its last `phase=verify` line is `DONE` (PASS) and no later `delta=INVALIDATED` line exists for it.
   Continue from the first phase or stage that is not done.
4. Never redo a done stage. If the world looks different from the journal, delegate a verifier run for the done stages before continuing, and invalidate those that fail.
5. If the last journal line is `delta=EMERGENCY`, do nothing until the user confirms the setup is safe.

## Fallback without subagents

If your agent cannot start subagents, run the roles as sequential phases yourself:

1. Before each phase, say which role you take and load that role's skill.
2. Work only from files in the task folder, not from earlier chat history.
3. Write the role's report file and one journal line before switching roles.
4. Keep the builder and the verifier as separate phases: finish and record the build before starting the check.

## Context hygiene

- Never call robot tools with `detail: full` yourself.
- Do not open detailed reports unless a decision needs them.
- Raw data (scans, long lists) belongs in files, not in replies.
- Keep the final message to the user short: result, what was built, path to journal.md.
