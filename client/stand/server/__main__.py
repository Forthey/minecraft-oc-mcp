"""CLI: python -m stand.server setup | start | stop | status."""

from __future__ import annotations

import argparse
import sys

from stand.config import load_config
from stand.server import process, setup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stand.server")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_setup = sub.add_parser("setup", help="install Java check, Forge, mods, configs, world template")
    p_setup.add_argument("--pin", action="store_true", help="write sha256 of mods into mods.yaml")
    p_setup.add_argument("--fresh-template", action="store_true", help="recreate the world template")
    sub.add_parser("start", help="start the server and wait for RCON")
    sub.add_parser("stop", help="stop the server")
    sub.add_parser("status", help="print whether the server answers RCON")
    args = parser.parse_args(argv)
    cfg = load_config()

    if args.cmd == "setup":
        if args.fresh_template:
            setup.check_java(cfg)
            setup.create_template(cfg, force=True)
        else:
            setup.setup_all(cfg, pin=args.pin)
        return 0
    if args.cmd == "start":
        if process.is_running(cfg):
            print("already running")
            return 0
        setup.check_java(cfg)
        proc = process.start_server(cfg)
        process.wait_rcon(cfg, proc=proc)
        print("running")
        return 0
    if args.cmd == "stop":
        process.stop_server(cfg)
        print("stopped")
        return 0
    running = process.is_running(cfg)
    print("running" if running else "not running")
    return 0 if running else 1


if __name__ == "__main__":
    sys.exit(main())
