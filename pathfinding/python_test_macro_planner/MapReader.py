import math
import os
from pathlib import Path

import anvil


class RegionReader:
    """Читает блоки из файлов регионов Minecraft (формат Anvil)."""

    def __init__(self, world_path: str):
        self.world_path = Path(world_path)
        self.region_dir = self.world_path / "region"

    @staticmethod
    def world_to_region(x: int, z: int) -> tuple[int, int]:
        """Преобразует мировые координаты в координаты региона."""
        region_x = math.floor(x / 512)
        region_z = math.floor(z / 512)
        return region_x, region_z

    def get_region_file(self, x: int, z: int) -> Path:
        region_x, region_z = self.world_to_region(x, z)
        return self.region_dir / f"r.{region_x}.{region_z}.mca"

    def read_block(self, x: int, y: int, z: int) -> anvil.Block | None:
        """Читает блок по абсолютным мировым координатам."""
        region_file = self.get_region_file(x, z)
        if not region_file.exists():
            return None  # Регион ещё не сгенерирован

        region = anvil.Region.from_file(str(region_file))

        # Локальные координаты внутри региона (0..511)
        local_x = x - math.floor(x / 512) * 512
        local_z = z - math.floor(z / 512) * 512

        # Локальные координаты чанка внутри региона (0..31)
        chunk_x = local_x // 16
        chunk_z = local_z // 16

        chunk = anvil.Chunk.from_region(region, chunk_x, chunk_z)

        # Локальные координаты блока внутри чанка (0..15)
        block_x = local_x % 16
        block_z = local_z % 16

        return chunk.get_block(block_x, y, block_z, force_new=True)


# --- Пример использования ---
if __name__ == "__main__":
    # Укажите путь к папке вашего мира
    WORLD_PATH = "/home/ivan/.minecraft/saves/Новый мир-/"

    reader = RegionReader(WORLD_PATH)

    # Пример: координаты, полученные от робота
    robot_x, robot_y, robot_z = map(int, input().split())

    block = reader.read_block(robot_x, robot_y, robot_z)
    if block is not None:
        print(f"Блок в точке ({robot_x}, {robot_y}, {robot_z}): {block.id}")
        print(f"Свойства: {block.properties}")
    else:
        print("Регион с этой точкой ещё не сгенерирован.")