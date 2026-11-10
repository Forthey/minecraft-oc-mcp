import json

from stand.runner.report import build_summary, render_report, write


def _results(status, scenario="s01-wall", agent="claude", duration=10.0, calls=12, cost=0.5, **extra):
    return {"run_id": f"{scenario}-{agent}-{status}-{duration}", "scenario": scenario, "agent": agent,
            "status": status, "duration_s": duration, "calls_total": calls,
            "usage": {"cost_usd": cost, "input_tokens": 1000, "output_tokens": 100},
            "judge": {"mode": "fixed", "passed": status == "PASS", "accuracy": 1.0 if status == "PASS" else 0.5,
                      "extra_count": 0, "details": {"missing": [{"pos": [1, 2, 3]}], "wrong": [], "extra": []}},
            "violations": [], "claimed_success": status == "PASS", "false_success": False, **extra}


def _write_runs(tmp_path, results):
    for i, r in enumerate(results):
        d = tmp_path / f"run{i}"
        d.mkdir()
        (d / "results.json").write_text(json.dumps(r), encoding="utf-8")


def test_summary_pass_rate(tmp_path):
    _write_runs(tmp_path, [_results("PASS", duration=10), _results("PASS", duration=30), _results("FAIL", duration=20)])
    text = build_summary(tmp_path)
    row = next(line for line in text.splitlines() if line.startswith("| s01-wall"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[:4] == ["s01-wall", "claude", "3", "2/3"]
    assert cells[4] == "20.0"


def test_summary_counts_skipped_separately(tmp_path):
    _write_runs(tmp_path, [_results("PASS"), {"scenario": "s01-wall", "agent": "claude", "status": "SKIPPED"}])
    row = next(line for line in build_summary(tmp_path).splitlines() if line.startswith("| s01-wall"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[2] == "1" and cells[3] == "1/1" and cells[-1] == "1"


def test_report_mentions_violations_with_log_line(tmp_path):
    r = _results("FAIL", violations=[{"rule": "repeated_call", "detail": "move_to x3", "log_line": 7}])
    text = render_report(r)
    assert "FAIL" in text and "repeated_call" in text and "action_log.jsonl:7" in text
    assert "[1, 2, 3]" in text


def test_write_creates_both_files(tmp_path):
    write(tmp_path, _results("PASS"))
    assert json.loads((tmp_path / "results.json").read_text())["status"] == "PASS"
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith("# ")
