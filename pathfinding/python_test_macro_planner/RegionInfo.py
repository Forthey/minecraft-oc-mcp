from dataclasses import dataclass, field
from RegionCoord import RegionCoord


@dataclass
class RegionInfo:
    coord: RegionCoord
    exists: bool
    cost_factor: float
    void_fraction: float = 0.0
    missing_fraction: float = 0.0
    samples_count: int = 0
    avg_delta: float = 0.0
    samples: list = field(default_factory=list)