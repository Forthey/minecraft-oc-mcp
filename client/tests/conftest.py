import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# tools/ нужен старым тестам валидатора (import validate_skills), корень нужен
# тестам стенда (import stand, tools.validate_skills).
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
