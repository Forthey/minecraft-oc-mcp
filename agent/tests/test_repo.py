from pathlib import Path

from validate_skills import validate_repo


def test_repo_valid():
    assert validate_repo(Path(__file__).resolve().parents[1]) == []
