from dataclasses import dataclass, field
import math

@dataclass(frozen=True)
class RegionCoord:
    x: int
    z: int

    @classmethod
    def from_world(cls, wx: float, wz: float) -> "RegionCoord":
        return cls(math.floor(wx / 512), math.floor(wz / 512))

    def bounds(self) -> tuple[int, int, int, int]:
        """Возвращает (min_x, max_x, min_z, max_z) в мировых координатах."""
        x0 = self.x * 512
        z0 = self.z * 512
        return x0, x0 + 511, z0, z0 + 511