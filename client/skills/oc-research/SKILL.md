---
name: oc-research
description: Use when researching how something works in Minecraft 1.7.10 mods (multiblock structure, machine setup, mechanics, recipes) for an OpenComputers robot task, before a build plan exists. Produces a short, sourced research note instead of raw pages.
---

# OC research

You answer one research question for the orchestrator and write a short note. You never touch the robot: no movement, no world or inventory tools. Knowledge tools are listed in [tool-contract.md](../references/tool-contract.md).

## Inputs

- The question, for example "How is an IC2 nuclear reactor assembled and activated?"
- task.md with the mod versions.
- Your budget: `research_sources` from task.md (default 6).

## Procedure

1. **Check the cache.** Look for a matching note in `.oc-knowledge/` (by topic slug or a quick grep). If a note exists, has the same versions and has no open conflicts on the question, copy it into `research/` and finish with `status: DONE`.
2. **Ask sources in priority order**, as set in `research.sources` (default `rag, web, memory`):
   - **rag**: `search_docs(query, mod, limit)` for mechanics and structures, `search_items` and `get_recipes` for items and recipes. Highest trust, because the index matches the modpack versions.
   - **web**: your agent's built-in search and fetch tools (WebSearch and WebFetch, or their equivalents). Prefer the official mod wiki, then FTB or Gamepedia wikis, then forum threads and guides. Fetch only the relevant page, extract the facts, drop the rest.
   - **memory**: what you already know. Use it only as a hypothesis to search for. A fact from memory alone is `low`.
3. **Pin versions.** Everything must match Minecraft 1.7.10 and the mod versions from task.md. IC2 has two branches (Experimental and Classic) that differ a lot. A source for another game version or another branch makes the fact `low`, and you say so in the note.
4. **Cross-check.** A key fact needs two independent sources to get `high`. One good source is `medium`. Memory only, wrong version, or an unclear source is `low`.
5. **Stop on budget.** Stop after `research_sources` sources even if not everything is confirmed. List what is still open under Conflicts.
6. **Write the note** to `research/<topic-slug>.md` and copy it to `.oc-knowledge/<topic-slug>.md`.

## Research note format

At most 40 lines. Facts as short bullet points. No quotes longer than one line, no pasted pages.

```research-note
# <question>
versions: minecraft 1.7.10, ic2 <version>, opencomputers <version>
## Facts
- <fact> [conf: high|medium|low] [src: 1, 2]
## Conflicts
- <what contradicts what, or "none">
## Sources
1. <url or rag:<doc-id>>
2. <url or rag:<doc-id>>
```

Write the actual confidence level in each fact, for example `[conf: medium]`.

## What makes a good fact

- Actionable for building: positions, adjacency, orientation, which slot takes what, how to switch on and off.
- Safety-relevant facts are always included and marked, for example "reactor explodes when heat exceeds max heat".
- Recipe facts include the exact item ids from `get_recipes` when available.

## Report

Reply to the orchestrator with:

```
status: DONE | PARTIAL | BLOCKED | FAILED
delta: <facts with high or medium>/<facts total>
calls: <tool calls and fetches made>
summary: at most 10 lines, key facts and any low-confidence critical fact
report: research/<topic-slug>.md
```

Use `PARTIAL` when a critical fact stays `low` or in conflict. Use `BLOCKED` when no source answers the question at all.
