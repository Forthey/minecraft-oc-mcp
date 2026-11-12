"""CLI runner.

python -m stand.runner run --scenario <id> --agent <name> [--repeat N] [--fresh] [--profile p] [--keep-workspace]
python -m stand.runner suite --agents a,b [--scenarios s01-wall,s02-craft] [--repeat N] [--profile p]
python -m stand.runner prepare --scenario <id> [--fresh]   сбросить регион и поставить сцену
python -m stand.runner judge --scenario <id>               оценить текущий мир без агента
python -m stand.runner report                              пересобрать stand/runs/summary.md
"""

from __future__ import annotations

import argparse
import json
import sys

from stand.config import load_config
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.runner import report
from stand.runner.agents import load_agents
from stand.runner.run import RUNS_DIR, evaluate, find_scenario, prepare, run_one
from stand.scenario import SCENARIOS_DIR, list_scenarios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stand.runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run one scenario with one agent")
    p_run.add_argument("--scenario", required=True)
    p_run.add_argument("--agent", required=True)
    p_run.add_argument("--repeat", type=int, default=1)
    p_run.add_argument("--fresh", action="store_true", help="full world reset before the first run")
    p_run.add_argument("--profile", default=None, help="override the scenario capability profile")
    p_run.add_argument("--keep-workspace", action="store_true", help="do not delete the agent workspace")

    p_suite = sub.add_parser("suite", help="run scenarios for several agents and rebuild the summary")
    p_suite.add_argument("--agents", required=True, help="comma separated agent names")
    p_suite.add_argument("--scenarios", default=None, help="comma separated scenario ids, default all")
    p_suite.add_argument("--repeat", type=int, default=1)
    p_suite.add_argument("--profile", default=None)

    sub.add_parser("report", help="rebuild stand/runs/summary.md")

    p_prep = sub.add_parser("prepare", help="reset the region and set up the scene")
    p_prep.add_argument("--scenario", required=True)
    p_prep.add_argument("--fresh", action="store_true")

    p_judge = sub.add_parser("judge", help="judge the current world")
    p_judge.add_argument("--scenario", required=True)

    args = parser.parse_args(argv)
    cfg = load_config()

    if args.cmd == "report":
        print(report.write_summary(RUNS_DIR))
        return 0

    agents = load_agents()
    if args.cmd == "suite":
        names = args.agents.split(",")
        unknown = [n for n in names if n not in agents]
        if unknown:
            parser.error(f"unknown agents {', '.join(unknown)}, known: {', '.join(agents)}")
        ids = args.scenarios.split(",") if args.scenarios else [p.parent.name for p in list_scenarios(SCENARIOS_DIR)]
        failures = 0
        for sid in ids:
            scenario = find_scenario(sid)
            for name in names:
                for n in range(1, args.repeat + 1):
                    try:
                        run_dir = run_one(cfg, scenario, agents[name], n, profile=args.profile)
                        status = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))["status"]
                        print(f"{status:8} {run_dir}")
                    except Exception as e:  # noqa: BLE001 - один сломанный прогон не останавливает набор
                        failures += 1
                        print(f"ERROR    {sid} {name} {n}: {type(e).__name__}: {e}")
        print(report.write_summary(RUNS_DIR))
        return 1 if failures else 0

    scenario = find_scenario(args.scenario)

    if args.cmd == "prepare":
        prepare(cfg, scenario, Knowledge.load(KNOWLEDGE_DIR, scenario.knowledge), args.fresh)
        print(f"scene of {scenario.id} is ready")
        return 0

    if args.cmd == "judge":
        from stand.runner.reset import ensure_server

        ensure_server(cfg)
        result = evaluate(cfg, scenario, Knowledge.load(KNOWLEDGE_DIR, scenario.knowledge))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["passed"] else 1

    if args.agent not in agents:
        parser.error(f"unknown agent {args.agent}, known: {', '.join(agents)}")
    for n in range(1, args.repeat + 1):
        run_dir = run_one(cfg, scenario, agents[args.agent], n, fresh=args.fresh and n == 1,
                          profile=args.profile, keep_workspace=args.keep_workspace)
        results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        print(f"{results['status']:8} {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
