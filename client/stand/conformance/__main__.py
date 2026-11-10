"""CLI: python -m stand.conformance --mcp fake|real.

Печатает таблицу проверок и возвращает код 1, если хотя бы одна не прошла.
Для real сцену из stand/conformance/scenario.yaml должен заранее подготовить
real_setup (робот у склада, в складе булыжник, камень в занятой клетке).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import anyio

from stand.conformance.checks import connect, load_scene, run_checks
from stand.config import load_config


async def _run(target: str, cfg, scene):
    async with connect(target, cfg, scene) as session:
        return await run_checks(session, scene)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stand.conformance")
    parser.add_argument("--mcp", choices=["fake", "real"], default="fake")
    args = parser.parse_args(argv)
    cfg = load_config()
    scene = load_scene()

    if args.mcp == "real":
        if not (cfg.real.get("command") or cfg.real.get("url")):
            raise SystemExit(
                "real MCP is not configured: set real.command or real.url "
                "in stand/config.yaml or stand/config.local.yaml"
            )
        if cfg.real.get("real_setup"):
            subprocess.run([*cfg.real["real_setup"], str(scene["scenario_path"])], check=True)

    results = anyio.run(_run, args.mcp, cfg, scene)
    width = max(len(r.name) for r in results)
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name:<{width}}  {r.detail}")
    passed = sum(r.ok for r in results)
    print(f"\n{passed}/{len(results)} checks passed ({args.mcp} MCP)")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
