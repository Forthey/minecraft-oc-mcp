import json

import pytest

from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.runner.agents import AgentRun
from stand.runner.metrics import collect
from stand.runner.usage import parse_usage, tool_inputs
from stand.scenario import SCENARIOS_DIR, load_scenario

HARNESS = {"budgets": {"robot_calls_per_stage": 150}}
PASSED = {"mode": "fixed", "passed": True, "accuracy": 1.0, "extra_count": 0, "details": {}}
FAILED = {"mode": "fixed", "passed": False, "accuracy": 0.5, "extra_count": 0, "details": {}}
OK_RUN = AgentRun(0, False, 42.0)
NO_USAGE = {"input_tokens": None, "output_tokens": None, "cached_input_tokens": None, "cost_usd": None,
            "final_text": "Done.", "num_turns": None}


@pytest.fixture(scope="module")
def s01():
    return load_scenario(SCENARIOS_DIR / "s01-wall" / "scenario.yaml")


@pytest.fixture(scope="module")
def k():
    return Knowledge.load(KNOWLEDGE_DIR)


def _log(run_dir, entries):
    with open(run_dir / "action_log.jsonl", "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps({"ok": True, "error_code": None, "fault": False, "data": {}, **e}) + "\n")


def _journal(run_dir, lines):
    d = run_dir / "journal" / "20261110-1200-wall"
    d.mkdir(parents=True, exist_ok=True)
    (d / "journal.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


def _line(phase, stage, status, calls=3, budget="-", role="builder"):
    return (f"[2026-11-10T12:00:00] phase={phase} stage={stage} role={role} status={status} "
            f"delta=1/1 calls={calls} budget={budget}")


def _collect(tmp_path, s, k, judge=PASSED, run=OK_RUN, usage=NO_USAGE, kind="none"):
    return collect(tmp_path, s, k, judge, run, usage, HARNESS, kind)


def _rules(results):
    return [v["rule"] for v in results["violations"]]


def test_repeated_failing_call_detected(tmp_path, s01, k):
    call = {"tool": "move_to", "args": {"x": 1, "y": 64, "z": 1}, "ok": False, "error_code": "NO_PATH"}
    _log(tmp_path, [call, {"tool": "get_status", "args": {}}, call, call, call])
    r = _collect(tmp_path, s01, k)
    leaks = [v for v in r["violations"] if v["rule"] == "repeated_call"]
    assert len(leaks) == 1 and leaks[0]["log_line"] == 4


def test_two_identical_not_violation(tmp_path, s01, k):
    call = {"tool": "move_to", "args": {"x": 1, "y": 64, "z": 1}, "ok": False, "error_code": "NO_PATH"}
    other = dict(call, error_code="BLOCKED")
    ok_call = dict(call, ok=True, error_code=None)
    _log(tmp_path, [call, call, other, ok_call, ok_call, ok_call])
    assert "repeated_call" not in _rules(_collect(tmp_path, s01, k))


def test_calls_and_errors_counted(tmp_path, s01, k):
    _log(tmp_path, [
        {"tool": "get_status", "args": {}},
        {"tool": "storage_take", "args": {}},
        {"tool": "place_at", "args": {}, "ok": False, "error_code": "NO_PATH"},
        {"tool": "place_at", "args": {}},
    ])
    r = _collect(tmp_path, s01, k)
    assert r["calls_total"] == 4
    assert r["calls_by_group"] == {"state": 1, "inventory": 1, "world": 2}
    assert r["errors_by_code"] == {"NO_PATH": 1}


def test_fault_reaction(tmp_path, s01, k):
    _log(tmp_path, [
        {"tool": "place_at", "args": {"x": 1}, "ok": False, "error_code": "CONNECTION_LOST", "fault": True},
        {"tool": "get_status", "args": {}},
    ])
    r = _collect(tmp_path, s01, k)
    assert r["faults"] == [{"log_line": 1, "tool": "place_at", "error_code": "CONNECTION_LOST", "next_tool": "get_status"}]


def test_done_without_verify(tmp_path, s01, k):
    _journal(tmp_path, [_line("build", "1-wall", "DONE"), _line("final", "-", "DONE", role="orchestrator")])
    assert "done_without_verify" in _rules(_collect(tmp_path, s01, k))
    _journal(tmp_path, [_line("build", "1-wall", "DONE"), _line("verify", "1-wall", "DONE", role="verifier"),
                        _line("final", "-", "DONE", role="orchestrator")])
    assert "done_without_verify" not in _rules(_collect(tmp_path, s01, k))


def test_dig_near_structure(tmp_path, s01, k):
    _log(tmp_path, [
        {"tool": "place_at", "args": {}, "data": {"pos": [100, 64, 100]}},
        {"tool": "move_to", "args": {"policy": "dig_through"}, "data": {"pos": [5, 5, 5], "dug": [[101, 64, 100]]}},
        {"tool": "move_to", "args": {"policy": "dig_through"}, "data": {"pos": [5, 5, 5], "dug": [[110, 64, 100]]}},
    ])
    r = _collect(tmp_path, s01, k)
    digs = [v for v in r["violations"] if v["rule"] == "dig_near_structure"]
    assert len(digs) == 1 and digs[0]["log_line"] == 2


def test_swing_near_structure(tmp_path, s01, k):
    _log(tmp_path, [
        {"tool": "place_at", "args": {}, "data": {"pos": [100, 64, 100]}},
        {"tool": "swing", "args": {"side": "front"}, "data": {"pos": [101, 64, 100]}},
        {"tool": "swing", "args": {"side": "front"}, "data": {"pos": [110, 64, 100]}},
    ])
    digs = [v for v in _collect(tmp_path, s01, k)["violations"] if v["rule"] == "dig_near_structure"]
    assert len(digs) == 1 and digs[0]["log_line"] == 2


def test_place_counts_as_placed(tmp_path, s01, k):
    _log(tmp_path, [
        {"tool": "place", "args": {"side": "front"}, "data": {"pos": [100, 64, 100]}},
        {"tool": "swing", "args": {"side": "up"}, "data": {"pos": [100, 65, 100]}},
    ])
    digs = [v for v in _collect(tmp_path, s01, k)["violations"] if v["rule"] == "dig_near_structure"]
    assert len(digs) == 1 and digs[0]["log_line"] == 2


def test_budget_exceeded(tmp_path, s01, k):
    _journal(tmp_path, [_line("build", "1-wall", "PARTIAL", budget="stage_redelegations:3/2"),
                        _line("build", "1-wall", "DONE", calls=151)])
    rules = _rules(_collect(tmp_path, s01, k))
    assert rules.count("budget_exceeded") == 2


def test_status_asked(tmp_path, s01, k):
    r = _collect(tmp_path, s01, k, judge=FAILED, usage=dict(NO_USAGE, final_text="Which wood type should I use?"))
    assert r["status"] == "ASKED"


def test_status_crash_and_timeout(tmp_path, s01, k):
    assert _collect(tmp_path, s01, k, judge=FAILED, run=AgentRun(1, False, 3.0))["status"] == "CRASH"
    assert _collect(tmp_path, s01, k, judge=PASSED, run=AgentRun(1, False, 3.0))["status"] == "PASS"
    assert _collect(tmp_path, s01, k, judge=FAILED, run=AgentRun(None, True, 900.0))["status"] == "TIMEOUT"


def test_false_success(tmp_path, s01, k):
    _journal(tmp_path, [_line("verify", "1-wall", "DONE", role="verifier"), _line("final", "-", "DONE", role="orchestrator")])
    r = _collect(tmp_path, s01, k, judge=FAILED)
    assert r["claimed_success"] is True and r["false_success"] is True and r["status"] == "FAIL"


def test_missing_journal_and_transcript(tmp_path, s01, k):
    r = _collect(tmp_path, s01, k, judge=FAILED, run=AgentRun(0, False, 1.0),
                 usage=parse_usage("claude_stream_json", tmp_path / "transcript.jsonl"))
    assert r["claimed_success"] is False
    assert r["calls_total"] == 0
    assert r["usage"]["cost_usd"] is None
    assert r["status"] == "FAIL"


def test_answer_leak(tmp_path, s01, k):
    events = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/stand/scenarios/s01-wall/scenario.yaml"}}]}},
        {"type": "result", "result": "done", "total_cost_usd": 0.1, "usage": {"input_tokens": 1, "output_tokens": 2}},
    ]
    (tmp_path / "transcript.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    usage = parse_usage("claude_stream_json", tmp_path / "transcript.jsonl")
    r = _collect(tmp_path, s01, k, usage=usage, kind="claude_stream_json")
    assert "answer_leak" in _rules(r)


def test_spec_accuracy(tmp_path, s01, k):
    d = _journal(tmp_path, [_line("final", "-", "DONE", role="orchestrator")])
    blocks = [{"pos": [x, y, 0], "item": "minecraft:cobblestone"} for x in range(3) for y in range(3)]
    blocks[0]["item"] = "minecraft:planks"
    spec = {"origin": [100, 64, 100], "stages": [{"id": "1-wall", "blocks": blocks}]}
    (d / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    r = _collect(tmp_path, s01, k)
    assert r["spec_accuracy"] == {"accuracy": pytest.approx(8 / 9), "extra": 0}


def test_claude_usage_parse(tmp_path):
    events = [
        {"type": "system", "subtype": "init"},
        {"type": "result", "result": "Wall built.", "total_cost_usd": 0.42, "num_turns": 7,
         "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50}},
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\nnot json\n", encoding="utf-8")
    u = parse_usage("claude_stream_json", path)
    assert u == {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 50, "cost_usd": 0.42,
                 "final_text": "Wall built.", "num_turns": 7, "agent_error": None}


def test_claude_input_includes_cache_creation(tmp_path):
    # Как у opencode: вход это всё некэшированное (с записью в кэш), чтение кэша отдельно.
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"type": "result", "result": "ok", "usage": {
        "input_tokens": 50, "cache_creation_input_tokens": 43916, "cache_read_input_tokens": 945689,
        "output_tokens": 10653}}), encoding="utf-8")
    u = parse_usage("claude_stream_json", path)
    assert (u["input_tokens"], u["cached_input_tokens"]) == (43966, 945689)


def test_codex_usage_parse(tmp_path):
    events = [
        {"type": "item.completed", "item": {"type": "agent_message", "text": "first"}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "arguments": {"x": 1}}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Built."}},
        {"type": "turn.completed", "usage": {"input_tokens": 5, "cached_input_tokens": 1, "output_tokens": 3}},
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    u = parse_usage("codex_json", path)
    assert (u["input_tokens"], u["output_tokens"], u["cached_input_tokens"]) == (15, 5, 5)
    assert u["final_text"] == "Built." and u["cost_usd"] is None
    assert any('"x": 1' in t for t in tool_inputs("codex_json", path))


def test_opencode_usage_parse(tmp_path):
    events = [{"type": "text", "part": {"type": "text", "text": "Done"}}]
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps(events[0]), encoding="utf-8")
    assert parse_usage("opencode_json", path)["final_text"] == "Done"


def test_opencode_usage_tokens_from_step_finish(tmp_path):
    def step(i, o, cached, cost):
        return {"type": "step_finish", "part": {"type": "step-finish", "cost": cost,
                "tokens": {"input": i, "output": o, "reasoning": 0, "cache": {"read": cached, "write": 0}}}}
    events = [step(100, 10, 5, 0.01), {"type": "text", "part": {"type": "text", "text": "Done"}}, step(200, 20, 0, 0.02)]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    u = parse_usage("opencode_json", path)
    assert (u["input_tokens"], u["output_tokens"], u["cached_input_tokens"], u["num_turns"]) == (300, 30, 5, 2)
    assert u["cost_usd"] == pytest.approx(0.03)
    assert u["final_text"] == "Done"


def test_non_utf8_transcript(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_bytes(b"\xff\xfe garbage\n" + json.dumps({"type": "result", "result": "ok"}).encode())
    assert parse_usage("claude_stream_json", path)["final_text"] == "ok"


def test_robot_calls_from_claude_transcript(tmp_path):
    from stand.runner.usage import robot_calls

    events = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "ToolSearch", "input": {}},
        {"type": "tool_use", "name": "mcp__robot__place_at", "input": {"x": 1, "y": 64, "z": 1, "item": "a:b"}},
    ]}}]
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps(events[0]), encoding="utf-8")
    calls = robot_calls("claude_stream_json", path)
    assert [c["tool"] for c in calls] == ["place_at"] and calls[0]["args"]["x"] == 1


def test_unknown_results_not_repeated_violation(tmp_path, s01, k):
    call = {"tool": "place_at", "args": {"x": 1}, "ok": None, "error_code": None}
    _log(tmp_path, [call, call, call])
    assert "repeated_call" not in _rules(_collect(tmp_path, s01, k))


def _write_events(tmp_path, events):
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    return path


def test_agent_error_opencode_quota(tmp_path):
    path = _write_events(tmp_path, [
        {"type": "text", "part": {"type": "text", "text": "Working"}},
        {"type": "error", "error": {"type": "provider.quota", "message": "Free usage limit reached.", "status": 429}},
    ])
    assert parse_usage("opencode_json", path)["agent_error"] == "provider.quota: Free usage limit reached."


def test_agent_error_claude_result(tmp_path):
    path = _write_events(tmp_path, [{"type": "result", "subtype": "error_during_execution", "is_error": True,
                                     "result": "API Error: 529 overloaded"}])
    assert parse_usage("claude_stream_json", path)["agent_error"] == "error_during_execution: API Error: 529 overloaded"


def test_agent_error_codex_turn_failed(tmp_path):
    path = _write_events(tmp_path, [{"type": "turn.failed", "error": {"message": "rate limit"}}])
    assert parse_usage("codex_json", path)["agent_error"] == "rate limit"


def test_agent_error_none_on_clean_run(tmp_path):
    path = _write_events(tmp_path, [{"type": "result", "subtype": "success", "is_error": False, "result": "ok"}])
    assert parse_usage("claude_stream_json", path)["agent_error"] is None
