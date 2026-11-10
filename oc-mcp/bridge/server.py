#!/usr/bin/env python3
import argparse
import os

from core import DEFAULT_LOG_FILE, Bridge
from tools import TOOLS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-file", default=os.environ.get("OC_MCP_LOG", DEFAULT_LOG_FILE))
    args = parser.parse_args()
    Bridge(TOOLS, host=args.host, port=args.port, log_file=args.log_file).serve_stdio()


if __name__ == "__main__":
    main()
