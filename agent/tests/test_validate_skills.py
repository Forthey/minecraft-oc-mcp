import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from validate_skills import (
    ALL_ERROR_CODES,
    JOURNAL_LINE_RE,
    check_body_length,
    check_frontmatter,
    check_links,
    contract_error_codes,
    contract_tools,
    load_skill,
    referenced_error_codes,
    referenced_tools,
)

ROOT = Path(__file__).resolve().parents[1]


def write_skill(tmp_path, dirname, name, description, body="x", extra=""):
    d = tmp_path / "skills" / dirname
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(f"---\nname: {name}\ndescription: {description}\n{extra}---\n{body}\n")
    return p


def section(text, heading):
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n## ")
    return heading + (rest if end == -1 else rest[:end])


def fenced(text, lang):
    marker = f"```{lang}\n"
    start = text.index(marker) + len(marker)
    return text[start:text.index("\n```", start)]


# Task 1: validator


def test_frontmatter_ok(tmp_path):
    p = write_skill(tmp_path, "oc-x", name="oc-x", description="Use when testing")
    assert check_frontmatter(load_skill(p)) == []


def test_frontmatter_name_mismatch(tmp_path):
    p = write_skill(tmp_path, "oc-x", name="oc-y", description="Use when testing")
    assert any("name" in e for e in check_frontmatter(load_skill(p)))


def test_frontmatter_description_prefix(tmp_path):
    p = write_skill(tmp_path, "oc-x", name="oc-x", description="Helps with stuff")
    assert any("Use when" in e for e in check_frontmatter(load_skill(p)))


def test_frontmatter_extra_field(tmp_path):
    p = write_skill(tmp_path, "oc-x", name="oc-x", description="Use when testing", extra="version: 1\n")
    assert any("version" in e for e in check_frontmatter(load_skill(p)))


def test_frontmatter_description_too_long(tmp_path):
    p = write_skill(tmp_path, "oc-x", name="oc-x", description="Use when " + "a" * 1100)
    assert any("1024" in e for e in check_frontmatter(load_skill(p)))


def test_missing_frontmatter_raises(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("no frontmatter\n")
    with pytest.raises(ValueError):
        load_skill(p)


def test_body_too_long(tmp_path):
    long_p = write_skill(tmp_path, "oc-a", name="oc-a", description="Use when x", body="\n".join(["l"] * 501))
    ok_p = write_skill(tmp_path, "oc-b", name="oc-b", description="Use when x", body="\n".join(["l"] * 500))
    assert len(check_body_length(load_skill(long_p))) == 1
    assert check_body_length(load_skill(ok_p)) == []


def test_broken_relative_link(tmp_path):
    p = write_skill(tmp_path, "oc-x", name="oc-x", description="Use when x", body="[x](../references/nope.md)")
    assert len(check_links(p)) == 1


def test_relative_link_with_anchor_ok(tmp_path):
    (tmp_path / "skills" / "references").mkdir(parents=True)
    (tmp_path / "skills" / "references" / "a.md").write_text("# A\n")
    p = write_skill(tmp_path, "oc-x", name="oc-x", description="Use when x", body="[x](../references/a.md#a)")
    assert check_links(p) == []


def test_http_link_ignored(tmp_path):
    p = write_skill(tmp_path, "oc-x", name="oc-x", description="Use when x", body="[x](https://a.b)")
    assert check_links(p) == []


def test_contract_tools_parsed(tmp_path):
    c = tmp_path / "tool-contract.md"
    c.write_text("| `move_to(x, y, z, policy)` | ... |\n| `dig(side)` | ... |\n## Error codes\n`BLOCKED`, `NO_PATH`\n")
    assert contract_tools(c) == {"move_to", "dig"}
    assert contract_error_codes(c) == {"BLOCKED", "NO_PATH"}


def test_unknown_tool_reported():
    assert referenced_tools("call `move_to(1,2,3)` then `fly(1)`", {"move_to"}) == {"fly"}


def test_agent_tools_not_reported():
    assert referenced_tools("use `WebSearch(q)`", set()) == set()


def test_unknown_error_code_reported():
    assert referenced_error_codes("got `NO_PATH` then `NO_FUEL`") == {"NO_FUEL"}


def test_journal_line_regex():
    ok = ("[2026-11-10T12:00:00] phase=build stage=1-structure role=builder status=DONE "
          "delta=9/9 calls=23 budget=stage_redelegations:0/2")
    assert JOURNAL_LINE_RE.match(ok)
    assert not JOURNAL_LINE_RE.match(ok.replace("DONE", "OK"))


# Task 2: contract and config

CONTRACT = ROOT / "skills/references/tool-contract.md"


def test_contract_has_all_tools():
    assert contract_tools(CONTRACT) == {
        "get_status", "world_info", "surroundings", "geo_scan", "move_to", "face", "move", "turn",
        "place_at", "place", "swing", "use", "inventory_scan", "inventory_transfer", "storage_scan",
        "storage_take", "storage_put", "equip", "craft_recipe", "craft", "nei_find", "nei_recipes",
        "nei_recipe", "nei_craft_tree", "nei_machine_plan", "search_docs", "verify_blocks", "get_action_log"}


def test_contract_error_codes():
    assert contract_error_codes(CONTRACT) == ALL_ERROR_CODES


def test_example_config_keys():
    cfg = yaml.safe_load((ROOT / "skills/references/examples/oc-harness.yaml").read_text())
    assert set(cfg) == {"versions", "warehouse", "autonomy", "budgets", "safety", "research"}
    assert cfg["budgets"] == {"step_attempts": 3, "stage_redelegations": 2, "design_revisions": 1,
                              "research_sources": 6, "robot_calls_per_stage": 150}
    assert cfg["autonomy"] in {"auto", "confirm-phases", "confirm-steps"}
    assert cfg["safety"]["require_confirm"] == ["insert_fuel", "activate_machine", "dig_near_structure"]
    assert cfg["research"] == {"sources": ["rag", "web", "memory"], "cache_dir": ".oc-knowledge"}


# Task 3: error handling

ERRORS_MD = ROOT / "skills/references/error-handling.md"


def test_error_table_covers_all_codes():
    table = section(ERRORS_MD.read_text(), "## Error table")
    assert {c for c in ALL_ERROR_CODES if f"`{c}`" in table} == ALL_ERROR_CODES


def test_error_handling_sections():
    text = ERRORS_MD.read_text()
    for h in ("## Error table", "## Anti-loop rules", "## Escalation ladder"):
        assert h in text


# Task 4: orchestrator


def test_orchestrator_sections():
    text = (ROOT / "skills/oc-orchestrator/SKILL.md").read_text()
    for h in ("## Phases", "## Task workspace", "## Journal", "## Delegation template",
              "## Budgets and escalation", "## When to ask the user", "## Resume",
              "## Fallback without subagents"):
        assert h in text
    assert "```journal" in text


# Task 5: research


def test_research_note_template():
    text = (ROOT / "skills/oc-research/SKILL.md").read_text()
    note = fenced(text, "research-note")
    for h in ("## Facts", "## Conflicts", "## Sources"):
        assert h in note
    assert "versions:" in note
    assert "[conf: high|medium|low]" in note


# Task 6: design and spec schema


def load_schema():
    return json.loads((ROOT / "skills/references/spec-schema.json").read_text())


def load_example():
    return json.loads((ROOT / "skills/references/examples/spec.example.json").read_text())


def test_example_spec_valid():
    jsonschema.validate(load_example(), load_schema())


def test_skill_inline_spec_valid():
    text = (ROOT / "skills/oc-design/SKILL.md").read_text()
    jsonschema.validate(json.loads(fenced(text, "json")), load_schema())


def test_gate_requires_known_value():
    bad = load_example()
    bad["stages"][0]["gate"] = "launch_rockets"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, load_schema())


def test_dangerous_gate_needs_emergency_off():
    bad = load_example()
    bad["emergency_off"] = None
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, load_schema())


def test_safe_spec_may_skip_emergency_off():
    text = (ROOT / "skills/oc-design/SKILL.md").read_text()
    wall = json.loads(fenced(text, "json"))
    assert wall["emergency_off"] is None
    jsonschema.validate(wall, load_schema())


# Task 7: supply and build


@pytest.mark.parametrize("skill,headings", [
    ("oc-supply", ("## Inputs", "## Procedure", "## BOM format", "## Missing resources", "## Report")),
    ("oc-build", ("## Inputs", "## Placement order", "## Error handling", "## Forbidden", "## Report")),
])
def test_role_skill_sections(skill, headings):
    text = (ROOT / f"skills/{skill}/SKILL.md").read_text()
    for h in headings:
        assert h in text


def test_build_forbids_supply():
    text = section((ROOT / "skills/oc-build/SKILL.md").read_text(), "## Forbidden")
    assert "`craft_recipe(" in text and "`craft(" in text and "`storage_take(" in text


# Task 8: verify


def test_verify_sections():
    text = (ROOT / "skills/oc-verify/SKILL.md").read_text()
    for h in ("## Structural check", "## Functional check", "## Allowed world changes",
              "## Emergency off", "## Report"):
        assert h in text
    assert "PASS" in text and "FAIL" in text


# Task 9: examples and scenarios


def test_workflow_examples_present():
    text = (ROOT / "skills/references/workflow-examples.md").read_text()
    for h in ("## Example 1", "## Example 2", "## Example 3", "## Example 4"):
        assert h in text


def test_orchestrator_links_examples():
    assert "../references/workflow-examples.md" in (ROOT / "skills/oc-orchestrator/SKILL.md").read_text()


@pytest.mark.parametrize("path", sorted((ROOT / "tests/scenarios").glob("0*.md")), ids=lambda p: p.name)
def test_scenario_format(path):
    text = path.read_text()
    for h in ("## Setup", "## Scripted tool responses", "## Expected behavior", "## Violations"):
        assert h in text


def test_scenarios_count():
    assert len(list((ROOT / "tests/scenarios").glob("0*.md"))) == 8


# Fixes from behavioral runs


def test_empty_final_acceptance_invalid():
    bad = load_example()
    bad["final_acceptance"] = []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, load_schema())


def test_build_covers_partial_stage():
    assert "## Partially built stage" in (ROOT / "skills/oc-build/SKILL.md").read_text()


def test_only_orchestrator_writes_status_lines():
    rules = section((ROOT / "skills/references/error-handling.md").read_text(), "## Anti-loop rules")
    assert "Only the orchestrator writes status lines" in rules


# Fixes from final review

from validate_skills import check_links_stay_inside


def test_gated_check_needs_emergency_off():
    text = (ROOT / "skills/oc-design/SKILL.md").read_text()
    spec = json.loads(fenced(text, "json"))
    spec["final_acceptance"][0]["gate"] = "insert_fuel"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(spec, load_schema())
    spec["emergency_off"] = "take the fuel out"
    jsonschema.validate(spec, load_schema())


def test_example_activation_check_is_gated():
    checks = load_example()["final_acceptance"]
    assert any(c.get("gate") == "activate_machine" for c in checks)


def test_skill_links_stay_inside_skills(tmp_path):
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "a.json").write_text("{}")
    p = write_skill(tmp_path, "oc-x", name="oc-x", description="Use when x", body="[a](../../examples/a.json)")
    assert len(check_links_stay_inside(p, tmp_path / "skills")) == 1


def test_no_journal_sections_left():
    for p in list((ROOT / "skills").rglob("*.md")) + list((ROOT / "tests/scenarios").glob("*.md")):
        text = p.read_text()
        assert "## Tried" not in text and "## Decisions" not in text, p


def test_no_path_first_reaction_is_safe():
    row = next(l for l in ERRORS_MD.read_text().splitlines() if l.startswith("| `NO_PATH`"))
    first = row.split("|")[2]
    assert "dig_through" not in first


def test_orchestrator_handles_failed_and_emergency():
    text = (ROOT / "skills/oc-orchestrator/SKILL.md").read_text()
    assert "delta=EMERGENCY" in text
    assert "`FAILED` from a builder" in text and "`FAILED` from a verifier" in text


def test_verify_uses_valid_status():
    assert "status `FAIL`" not in (ROOT / "skills/oc-verify/SKILL.md").read_text()


# Team contract doc stays in sync with skills/references/tool-contract.md

TEAM_DOC = ROOT / "docs/mcp-contract.md"


def team_doc_tools(text):
    import re
    names = set()
    for line in text.splitlines():
        if line.startswith("**`"):
            names.update(re.findall(r"\*\*`([a-z_]+)\(", line))
    return names


def test_team_contract_doc_in_sync():
    text = TEAM_DOC.read_text()
    assert team_doc_tools(text) == contract_tools(CONTRACT)
    codes = section(text, "## Коды ошибок")
    assert {c for c in ALL_ERROR_CODES if f"| `{c}` |" in codes} == ALL_ERROR_CODES


def test_tool_contract_points_to_team_doc():
    assert "docs/mcp-contract.md" in CONTRACT.read_text()


def test_supply_recomputes_tree_after_taking():
    """После storage_take дерево крафта считается заново: склад мог закрыть часть шагов."""
    text = section((ROOT / "skills/oc-supply/SKILL.md").read_text(), "## Procedure")
    take = text.index("`storage_take(")
    assert "`nei_craft_tree(" in text[take:], "nei_craft_tree must be called again after storage_take"
    assert "64" in text, "craft_recipe runs above 64 per grid slot must be split"


def test_design_does_not_expect_free_space_from_status():
    text = (ROOT / "skills/oc-design/SKILL.md").read_text()
    assert "where there is free space" not in text
