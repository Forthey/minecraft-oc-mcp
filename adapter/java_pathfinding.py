from __future__ import annotations

import json
import logging
from pathlib import Path

import anyio

from adapter.pose import Pos

log = logging.getLogger(__name__)

FACING_ARG = {"north": "North", "south": "South", "east": "East", "west": "West"}


class JavaPathfinder:
    def __init__(self, jar: Path | str, world_dir: Path | str, java: str = "java", timeout: float = 60,
                 long_range: int = 0):
        self.jar = str(jar)
        self.world_dir = str(world_dir)
        self.java = java
        self.timeout = timeout
        self.long_range = long_range

    def command(self, start: Pos, goal: Pos, facing: str) -> list[str]:
        return [self.java, "-jar", self.jar, "--cells", self.world_dir,
                *map(str, start), *map(str, goal), FACING_ARG.get(facing, "North")]

    async def route(self, start: Pos, goal: Pos, facing: str) -> list[Pos] | None:
        try:
            with anyio.fail_after(self.timeout):
                proc = await anyio.run_process(self.command(start, goal, facing), check=False)
        except (TimeoutError, OSError) as e:
            log.warning("java pathfinding failed: %s", e)
            return None
        if proc.returncode != 0:
            log.warning("java pathfinding exit %s: %s", proc.returncode, proc.stderr.decode(errors="replace")[-500:])
            return None
        return parse_cells(proc.stdout.decode(errors="replace"))


def parse_cells(text: str) -> list[Pos] | None:
    try:
        value = json.loads(text.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    if not isinstance(value, list) or not value:
        return None
    try:
        return [(int(p[0]), int(p[1]), int(p[2])) for p in value]
    except (TypeError, ValueError, IndexError):
        return None


def densify(path: list[Pos]) -> list[Pos]:
    out = [path[0]]
    for p in path[1:]:
        cur = out[-1]
        for axis in (1, 0, 2):
            while cur[axis] != p[axis]:
                step = 1 if p[axis] > cur[axis] else -1
                cur = tuple(c + step if i == axis else c for i, c in enumerate(cur))
                out.append(cur)
    return out
