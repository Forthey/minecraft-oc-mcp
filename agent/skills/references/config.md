# Harness configuration (oc-harness.yaml)

The orchestrator reads `oc-harness.yaml` from the project root before anything else. If the file is missing, use these defaults and copy the effective values into task.md. If only some keys are present, take the rest from the defaults.

## Keys

| Key | Type | Default | Meaning |
|---|---|---|---|
| `versions.minecraft` | string | `1.7.10` | Game version. Research must match it |
| `versions.ic2` | string | none | IC2 version in the modpack. If unset, ask the user before research |
| `versions.opencomputers` | string | none | OpenComputers version. Same rule as `ic2` |
| `warehouse.pos` | `[x, y, z]` | none | Position of the warehouse chest. The robot tools do not report it. If the key is missing, ask the user |
| `warehouse.side` | string | `north` | Side of the chest the robot stands at, then it faces the chest with `face` |
| `autonomy` | string | `confirm-phases` | How often to ask the user, see below |
| `budgets.step_attempts` | int | `3` | Attempts of one step inside a subagent |
| `budgets.stage_redelegations` | int | `2` | How many times the orchestrator re-runs one stage |
| `budgets.design_revisions` | int | `1` | Spec revisions before asking the user |
| `budgets.research_sources` | int | `6` | Sources consulted per research question |
| `budgets.robot_calls_per_stage` | int | `150` | Robot tool calls allowed per build stage |
| `safety.require_confirm` | list | `[insert_fuel, activate_machine, dig_near_structure]` | Actions that always need user confirmation |
| `research.sources` | list | `[rag, web, model]` | Source priority. `model` is the agent's own knowledge. Remove an entry to disable that source |
| `research.cache_dir` | string | `.oc-knowledge` | Shared research note cache |
| `memory.profile` | string | `player` | Player or team id for the `memory` server, see [memory.md](memory.md) |

## Autonomy modes

- `auto`: ask the user only for `safety.require_confirm` actions and when the escalation ladder is exhausted.
- `confirm-phases`: everything from `auto`, plus approval of the spec before supply starts.
- `confirm-steps`: everything from `confirm-phases`, plus approval before each build stage.

## Example

See [examples/oc-harness.yaml](examples/oc-harness.yaml).
