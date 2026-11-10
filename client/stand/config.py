"""Загрузка конфига стенда из stand/config.yaml и stand/config.local.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "stand" / "config.yaml"


@dataclass
class Config:
    """Настройки стенда. Все пути уже абсолютные."""

    java_path: str
    java_args: list[str]
    server_dir: Path
    world_template_dir: Path
    mods_manifest: Path
    mods_cache: Path
    rcon_host: str
    rcon_port: int
    rcon_password: str
    robot_mcp: str
    real: dict
    prompt_template: str
    spawn: tuple[int, int, int]
    spawn_radius: int
    root: Path = field(default=ROOT)

    @property
    def world_dir(self) -> Path:
        """Папка мира сервера."""
        return self.server_dir / "world"


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _abs(p: str, root: Path) -> Path:
    path = Path(p)
    return path if path.is_absolute() else root / path


def load_config(path: Path | None = None, root: Path = ROOT) -> Config:
    """Читает конфиг. Рядом лежащий config.local.yaml перекрывает ключи основного."""
    path = path or DEFAULT_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    local = path.with_name("config.local.yaml")
    if local.exists():
        data = _merge(data, yaml.safe_load(local.read_text(encoding="utf-8")) or {})
    rcon = data.get("rcon", {})
    return Config(
        java_path=data["java_path"],
        java_args=list(data.get("java_args", [])),
        server_dir=_abs(data["server_dir"], root),
        world_template_dir=_abs(data["world_template_dir"], root),
        mods_manifest=_abs(data["mods_manifest"], root),
        mods_cache=_abs(data["mods_cache"], root),
        rcon_host=rcon.get("host", "127.0.0.1"),
        rcon_port=int(rcon.get("port", 25575)),
        rcon_password=str(rcon.get("password", "")),
        robot_mcp=data.get("robot_mcp", "fake"),
        real=dict(data.get("real") or {}),
        prompt_template=data.get("prompt_template", "{goal}"),
        spawn=tuple(data.get("spawn", [100, 64, 100])),
        spawn_radius=int(data.get("spawn_radius", 96)),
        root=root,
    )
