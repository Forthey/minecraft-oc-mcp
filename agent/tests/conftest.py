import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
# Тесты валидатора импортируют его как модуль верхнего уровня (import validate_skills).
# Пакеты adapter, stand и agent ставит uv sync (корневой pyproject.toml).
sys.path.insert(0, str(AGENT_DIR / "tools"))
