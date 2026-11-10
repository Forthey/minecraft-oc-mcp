"""CLI runner.

python -m stand.runner run --scenario <id> --agent <name> [--repeat N] [--fresh] [--profile p] [--keep-workspace]
python -m stand.runner prepare --scenario <id> [--fresh]   сбросить регион и поставить сцену
python -m stand.runner judge --scenario <id>               оценить текущий мир без агента
"""

from __future__ import annotations

import argparse
import json
import sys

from stand.config import load_config
from stand.knowledge import KNOWLEDGE_DIR, Knowledge
from stand.runner.agents import load_agents
from stand.runner.run import evaluate, find_scenario, prepare, run_one


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

    p_prep = sub.add_parser("prepare", help="reset the region and set up the scene")
    p_prep.add_argument("--scenario", required=True)
    p_prep.add_argument("--fresh", action="store_true")

    p_judge = sub.add_parser("judge", help="judge the current world")
    p_judge.add_argument("--scenario", required=True)

    args = parser.parse_args(argv)
    cfg = load_config()
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

    agents = load_agents()
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
