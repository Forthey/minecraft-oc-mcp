# Workflow examples

Short traces of how a task should run. `->` is a delegation to a subagent or a tool call, the text after `->` on the same line is the reply.

## Example 1: plain wall, phases skipped

Goal: "Build a 3x3 cobblestone wall in front of you."

```
Orchestrator: get_status -> pos (10,64,10), facing north; warehouse (6,64,10) side east from oc-harness.yaml
  decisions.md: research SKIPPED (trivial structure, no mod mechanics)
  oc-design inline: spec.json, 1 stage "1-wall", 9 x minecraft:cobblestone, origin (10,64,9)
  acceptance: structural only, emergency_off null
-> Supplier: "supply spec.json"                 -> DONE, delta 9/9 items
     (move_to (7,64,10), face west, storage_scan front -> slot 1: 32x minecraft:cobblestone:0,
      storage_take front slot 1 count 9, inventory_scan -> slot 1: 9x minecraft:cobblestone:0)
-> Builder: "build stage 1-wall"                -> DONE, delta 9/9 blocks
-> Verifier: "verify stage 1-wall"              -> DONE, verdict PASS (verify_blocks: missing 0, wrong 0)
Result to user: "Wall built, verified 9/9. Journal: .oc-tasks/20261110-1200-wall/journal.md"
```

## Example 2: machine with a functional check

Goal: "Set up a working Macerator powered by a Generator."

```
-> Researcher A: "Macerator and Generator recipes, IC2 <ver>"   -> DONE, rag hit, conf high
-> Researcher B: "how to power a machine from a generator"      -> DONE, rag miss, web: 2 sources, conf high
   (A and B run in parallel)
Orchestrator: spec = generator next to macerator, 1 stage
   final_acceptance: {actions: [storage_put 1 coal into the generator fuel slot, storage_put 1 iron ore
                      into the macerator input slot, wait 20 s, storage_scan on the macerator],
                      expect: "iron dust in the output slot"}
   autonomy confirm-phases -> show spec to user -> approved
-> Supplier: nei_craft_tree IC2:blockMachine:3 -> steps: circuit x1, macerator x1; raw: copper cable
             storage_scan warehouse -> cable and casing there -> storage_take slots
             nei_craft_tree IC2:blockMachine:3 again -> steps now match the inventory, fresh recipe ids
             craft_recipe <circuit recipe id from this reply> 1 -> craft_recipe <macerator recipe id> 1
             -> DONE, delta 2/2 machines
-> Builder: "build stage 1-machines"            -> DONE, delta 2/2
-> Verifier: "verify stage 1-machines"          -> DONE, verdict PASS
-> Verifier: "final check"                      -> DONE, verdict PASS (dust in output slot)
```

## Example 3: IC2 reactor with gates and a failed check

Goal: "Build an IC2 nuclear reactor."

```
-> Researchers in parallel, cache checked first:
   A "reactor structure: block, chambers, activation"      -> DONE, rag + web
   B "safe component layout for <ver>, no overheating"     -> PARTIAL, conflict on vent cooling value, conf low
   C "recipes: reactor, chamber, layout components"         -> DONE, rag
Orchestrator: critical low fact -> Researcher D: "vent cooling value in IC2 <ver>" -> DONE, third source, conflict resolved
   oc-design: stages 1-structure, 2-cooling, 3-fuel (gate insert_fuel), 4-activate (gate activate_machine)
   emergency_off: "use the lever to switch off, storage_take the fuel rod from slot 2"
   final_acceptance: fuel rod durability drops; both vents still in place every 10 s for 60 s
   user approves spec
-> Supplier                                     -> PARTIAL: 4 x IC2:itemPlates:4 missing, cannot craft
   Orchestrator asks user: "Put 4 dense copper plates into the warehouse, or use the layout without chambers?"
   user adds plates -> Supplier                 -> DONE
-> Builder 1-structure -> DONE;  Verifier -> DONE, verdict PASS
-> Builder 2-cooling   -> DONE;  Verifier -> DONE, verdict PASS (storage_scan: slots match spec)
   gate insert_fuel -> user confirms
-> Builder 3-fuel      -> DONE;  Verifier -> DONE, verdict PASS
   gate activate_machine -> user confirms
-> Builder 4-activate  -> DONE
-> Verifier "final": storage_scan every 10 s -> vent in slot 3 gone after 30 s (melted)
   -> emergency_off first -> storage_scan: fuel slot empty -> DONE, verdict FAIL
   Journal: status=FAILED for the final check; tried.md: "- final: layout v1 (2 vents) -> vent melted"
Orchestrator: design_revisions 0/1 -> oc-design revises 2-cooling (4 vents), keeps 1-structure PASS
   journal: delta=INVALIDATED for 2-cooling, 3-fuel (fuel taken out by emergency_off), 4-activate
   -> Supplier for stage 2-cooling only (2 more vents) -> Builder 2-cooling -> Verifier PASS
   gate insert_fuel -> user confirms again -> Builder 3-fuel -> Verifier PASS
   gate activate_machine -> user confirms again -> Builder 4-activate -> final check PASS
```

## Example 4: loop avoided

```
BAD (forbidden):
  Builder: move_to(15,64,3, avoid) -> NO_PATH
           move_to(15,64,3, avoid) -> NO_PATH
           move_to(15,64,3, avoid) -> NO_PATH      third identical call, rule 1 broken
           ...

GOOD:
  Builder: move_to(15,64,3, avoid) -> NO_PATH
           move_to(15,64,3, dig_through) not allowed: placed structure next to target, no dig_near_structure gate
           move_to(16,64,3, avoid) (other approach position) -> NO_PATH
           tried.md: "- 1-structure: approach (15,64,3) and (16,64,3) -> NO_PATH"
           -> BLOCKED, delta 7/9, hypothesis: target enclosed by own blocks
  Orchestrator: re-plan, stage_redelegations 1/2: move block (5,0,-6) earlier in blocks order
  -> Builder (with tried.md lines in the delegation) -> DONE, delta 9/9
```
