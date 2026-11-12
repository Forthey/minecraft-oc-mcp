from RegionCoord import RegionCoord
from RegionInfo import RegionInfo
from pathlib import Path
from typing import Optional
import anvil
import math
import heapq


NON_SOLID = {
    "air", "cave_air", "void_air",
    "short_grass", "grass", "tall_grass",
    "fern", "large_fern", "dead_bush",
    "dandelion", "poppy", "blue_orchid", "allium",
    "azure_bluet", "red_tulip", "orange_tulip",
    "white_tulip", "pink_tulip", "oxeye_daisy",
    "cornflower", "lily_of_the_valley",
    "sunflower", "lilac", "rose_bush", "peony",
    "torch", "wall_torch", "soul_torch",
    "redstone_torch", "redstone_wall_torch",
    "vine", "glow_lichen",
    "lily_pad", "seagrass", "tall_seagrass",
    "kelp", "kelp_plant",
    "sugar_cane", "moss_carpet",
}

BIOME_COST = {
    "ocean": 0.8, "deep_ocean": 0.8, "warm_ocean": 0.8,
    "plains": 1.0, "desert": 1.0,
    "forest": 1.1, "birch_forest": 1.1,
    "taiga": 1.1, "jungle": 1.2, "swamp": 1.2,
    "mountains": 1.3, "windswept_hills": 1.3,
    "snowy_peaks": 1.5, "jagged_peaks": 1.5,
    "frozen_peaks": 1.5,
}
DEFAULT_BIOME_COST = 1.0
DEFAULT_HEIGHT = 64  # «средний» y для неизвестного чанка


def _is_chunk_not_found(e: Exception) -> bool:
    return "ChunkNotFound" in type(e).__name__


class RegionCostEstimator:
    def __init__(self, world_path: str,
                 top_y: int = 320, bottom_y: int = -64,
                 void_penalty: float = 5.0,
                 low_data_threshold: float = 0.2):
        self.region_dir = Path(world_path).expanduser().resolve() / "region"
        self.top_y = top_y
        self.bottom_y = bottom_y
        self.void_penalty = void_penalty
        # если меньше 20% клеток имеют реальные данные — используем дефолт
        self.low_data_threshold = low_data_threshold
        self._info_cache: dict[RegionCoord, RegionInfo] = {}
        self._region_cache: dict[RegionCoord, anvil.Region | None] = {}

    def estimate(self, coord: RegionCoord) -> RegionInfo:
        if coord in self._info_cache:
            return self._info_cache[coord]
        region = self._load_region(coord)
        if region is None:
            info = RegionInfo(coord, exists=False, cost_factor=3.0)
        else:
            grid, missing, voids = self._sample_grid(region, coord)
            info = self._compute_info(coord, grid, missing, voids)
        self._info_cache[coord] = info
        return info

    def debug(self, coord: RegionCoord) -> None:
        path = self.region_dir / f"r.{coord.x}.{coord.z}.mca"
        print(f"region_dir = {self.region_dir}")
        print(f"путь       = {path}")
        print(f"exists     = {path.exists()}")
        if not path.exists():
            return
        try:
            anvil.Region.from_file(str(path))
            print("парсинг    = OK")
        except Exception as e:
            print(f"парсинг    = FAIL: {type(e).__name__}: {e}")

    def _load_region(self, coord: RegionCoord) -> anvil.Region | None:
        if coord in self._region_cache:
            return self._region_cache[coord]
        path = self.region_dir / f"r.{coord.x}.{coord.z}.mca"
        if not path.exists():
            self._region_cache[coord] = None
            return None
        try:
            region = anvil.Region.from_file(str(path))
        except Exception as e:
            print(f"[RegionCostEstimator] ОШИБКА ПАРСИНГА {path}: "
                  f"{type(e).__name__}: {e}")
            self._region_cache[coord] = None
            return None
        self._region_cache[coord] = region
        return region

    def _sample_grid(self, region, coord: RegionCoord):
        """
        grid[ci][cj]:
            ('solid', y, biome)     — реальный террейн
            ('void', None, None)    — чанк есть, но всё до -64 воздух
            ('missing', None, None) — ChunkNotFound, чанк не сгенерирован
        Возвращает (grid, missing_count, void_count).
        """
        grid = [[None] * 32 for _ in range(32)]
        missing = 0
        voids = 0
        for ci in range(32):
            for cj in range(32):
                try:
                    chunk = anvil.Chunk.from_region(region, ci, cj)
                except Exception as e:
                    if _is_chunk_not_found(e):
                        grid[ci][cj] = ("missing", None, None)
                        missing += 1
                    continue
                y = self._find_surface(chunk, 8, 8)
                if y is None:
                    grid[ci][cj] = ("void", None, None)
                    voids += 1
                    continue
                biome = self._get_biome(chunk, 8, 8)
                grid[ci][cj] = ("solid", y, biome)
        return grid, missing, voids

    def _find_surface(self, chunk, bx: int, bz: int) -> Optional[int]:
        for y in range(self.top_y, self.bottom_y - 1, -1):
            try:
                b = chunk.get_block(bx, y, bz, force_new=True)
            except Exception:
                return None
            if b is None:
                continue
            if b.id not in NON_SOLID:
                return y
        return None

    def _get_biome(self, chunk, bx: int, bz: int) -> Optional[str]:
        for attr in ("get_biome", "biome_at"):
            fn = getattr(chunk, attr, None)
            if callable(fn):
                try:
                    b = fn(bx, bz)
                    if isinstance(b, str):
                        return b.replace("minecraft:", "")
                    v = getattr(b, "id", None) or getattr(b, "name", None)
                    return v.replace("minecraft:", "") if isinstance(v, str) else v
                except Exception:
                    pass
        try:
            biomes = chunk.data["Biomes"]
            if isinstance(biomes, (list, tuple)) and len(biomes) >= 256:
                val = biomes[bz * 16 + bx]
                if isinstance(val, str):
                    return val.replace("minecraft:", "")
                return f"biome_id:{val}"
            if isinstance(biomes, str):
                return biomes.replace("minecraft:", "")
        except (KeyError, AttributeError, IndexError, TypeError):
            pass
        return None

    def _cell_height(self, cell) -> Optional[int]:
        if cell is None:
            return None
        kind = cell[0]
        if kind == "solid":
            return cell[1]
        if kind == "missing":
            return DEFAULT_HEIGHT
        return None  # void

    def _compute_info(self, coord, grid, missing, voids) -> RegionInfo:
        solids = 1024 - missing - voids
        missing_frac = missing / 1024.0
        void_frac = voids / 1024.0

        # Слишком мало реальных данных — используем оптимистичный дефолт
        if solids < 1024 * self.low_data_threshold:
            if voids > missing:
                return RegionInfo(coord, exists=True,
                                  cost_factor=float("inf"),
                                  void_fraction=void_frac,
                                  missing_fraction=missing_frac,
                                  samples_count=solids)
            # mostly missing → считаем «средний незнакомый террейн»
            return RegionInfo(coord, exists=True, cost_factor=3.0,
                              void_fraction=void_frac,
                              missing_fraction=missing_frac,
                              samples_count=solids)

        traversal = self._region_traversal_cost(grid)
        if traversal is None:
            # Настоящий void-барьер (не «дырки missing» — те проходимы)
            return RegionInfo(coord, exists=True,
                              cost_factor=float("inf"),
                              void_fraction=void_frac,
                              missing_fraction=missing_frac,
                              samples_count=solids)

        # Средний |Δh| только по solid→solid для дебага
        total_delta, edges = 0.0, 0
        for ci in range(32):
            for cj in range(32):
                a = self._cell_height(grid[ci][cj])
                if a is None or grid[ci][cj][0] != "solid":
                    continue
                for di, dj in ((1, 0), (0, 1)):
                    ni, nj = ci + di, cj + dj
                    if not (0 <= ni < 32 and 0 <= nj < 32):
                        continue
                    if grid[ni][nj] is None or grid[ni][nj][0] != "solid":
                        continue
                    total_delta += abs(a - grid[ni][nj][1])
                    edges += 1
        avg_delta = total_delta / edges if edges else 0.0

        biomes = [c[2] for row in grid for c in row
                  if c is not None and c[2]]
        biome_factor = 1.0
        if biomes:
            biome_factor = sum(BIOME_COST.get(b, DEFAULT_BIOME_COST)
                               for b in biomes) / len(biomes)

        per_cell = traversal / 32.0
        cost = per_cell * (1.0 + self.void_penalty * void_frac) * biome_factor

        return RegionInfo(
            coord=coord, exists=True, cost_factor=cost,
            void_fraction=void_frac, missing_fraction=missing_frac,
            samples_count=solids, avg_delta=avg_delta,
        )

    def _region_traversal_cost(self, grid) -> Optional[float]:
        """
        2D A* по сетке. missing → проходим (y=64), void → непроходим.
        """
        def axis(starts, targets):
            heap, g = [], {}
            for s in starts:
                h = self._cell_height(grid[s[0]][s[1]])
                if h is None:
                    continue
                g[s] = 0.0
                heapq.heappush(heap, (0.0, s))
            if not heap:
                return None
            while heap:
                cost, (ci, cj) = heapq.heappop(heap)
                if (ci, cj) in targets:
                    return cost
                if cost > g.get((ci, cj), math.inf):
                    continue
                h0 = self._cell_height(grid[ci][cj])
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ni, nj = ci + di, cj + dj
                    if not (0 <= ni < 32 and 0 <= nj < 32):
                        continue
                    h1 = self._cell_height(grid[ni][nj])
                    if h1 is None:
                        continue
                    new_cost = cost + 1.0 + abs(h0 - h1)
                    if new_cost < g.get((ni, nj), math.inf):
                        g[(ni, nj)] = new_cost
                        heapq.heappush(heap, (new_cost, (ni, nj)))
            return None

        west  = [(0,  cj) for cj in range(32)]
        east  = {(31, cj) for cj in range(32)}
        north = [(ci, 0)  for ci in range(32)]
        south = {(ci, 31) for ci in range(32)}

        we = axis(west, east)
        ns = axis(north, south)
        if we is None and ns is None:
            return None
        if we is None:
            return ns
        if ns is None:
            return we
        return (we + ns) / 2.0