"""Установка сервера: проверка Java, Forge, моды, конфиги, шаблон мира.

Каждый шаг можно повторять: уже сделанное пропускается.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

import yaml

from stand.config import Config
from stand.rcon import Rcon
from stand.server import navmap, process

FORGE_VERSION = "1.7.10-10.13.4.1614-1.7.10"
FORGE_INSTALLER_URL = (
    "https://maven.minecraftforge.net/net/minecraftforge/forge/"
    f"{FORGE_VERSION}/forge-{FORGE_VERSION}-installer.jar"
)

# Слои плоского мира: bedrock, 59 stone, 3 dirt, grass. Верх пола на y=63.
GENERATOR_SETTINGS = "2;7,59x1,3x3,2;1;"


def java_major(java_path: str) -> int:
    """Возвращает основную версию Java (8 для 1.8.x)."""
    out = subprocess.run([java_path, "-version"], capture_output=True, text=True)
    text = out.stderr + out.stdout
    m = re.search(r'version "(\d+)(?:\.(\d+))?', text)
    if not m:
        raise RuntimeError(f"cannot parse java version from: {text.strip()[:200]}")
    first = int(m.group(1))
    return int(m.group(2)) if first == 1 and m.group(2) else first


def check_java(cfg: Config) -> None:
    """Проверяет, что java_path указывает на Java 8."""
    try:
        major = java_major(cfg.java_path)
    except FileNotFoundError as e:
        raise RuntimeError(f"java not found at {cfg.java_path}, set java_path in stand/config.yaml") from e
    if major != 8:
        raise RuntimeError(
            f"{cfg.java_path} is Java {major}, Forge 1.7.10 needs Java 8. "
            "Set java_path in stand/config.yaml or stand/config.local.yaml"
        )


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "oc-stand-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f)
    tmp.replace(dest)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def install_forge(cfg: Config) -> Path:
    """Ставит сервер Forge в server_dir и возвращает путь к universal jar."""
    cfg.server_dir.mkdir(parents=True, exist_ok=True)
    jar = process.forge_jar(cfg)
    if jar is not None:
        return jar
    installer = cfg.mods_cache / f"forge-{FORGE_VERSION}-installer.jar"
    if not installer.exists():
        _download(FORGE_INSTALLER_URL, installer)
    result = subprocess.run(
        [cfg.java_path, "-jar", str(installer), "--installServer"],
        cwd=cfg.server_dir,
        capture_output=True,
        text=True,
    )
    jar = process.forge_jar(cfg)
    if result.returncode != 0 or jar is None:
        failed = re.findall(r"(?:Failed to|Failed:).*", result.stdout + result.stderr)
        raise RuntimeError(
            "Forge installer failed. Missing libraries must be put into "
            f"{cfg.server_dir / 'libraries'} by hand.\n" + "\n".join(failed[-20:])
        )
    return jar


def install_mods(cfg: Config, manifest: Path, pin: bool = False) -> list[Path]:
    """Копирует моды из кэша в server_dir/mods, недостающие скачивает.

    При pin=True вписывает sha256 скачанных файлов в манифест вместо проверки.
    Jar верхнего уровня в mods/, которых нет в манифесте, удаляются: старая версия
    мода рядом с новой роняет Forge. Подпапки не трогаются, в mods/1.7.10
    CodeChickenCore держит свои библиотеки.
    """
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    mods_dir = cfg.server_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    wanted = {mod["file"] for mod in data["mods"]}
    for stale in mods_dir.glob("*.jar"):
        if stale.name not in wanted:
            stale.unlink()
    cfg.mods_cache.mkdir(parents=True, exist_ok=True)
    installed = []
    pinned: dict[str, str] = {}
    for mod in data["mods"]:
        cached = cfg.mods_cache / mod["file"]
        if not cached.exists():
            if not mod.get("url"):
                raise FileNotFoundError(
                    f"{mod['name']}: put {mod['file']} into {cfg.mods_cache} (mods-cache), no url given"
                )
            try:
                _download(mod["url"], cached)
            except OSError as e:
                raise FileNotFoundError(
                    f"{mod['name']}: download failed ({e}), put {mod['file']} into {cfg.mods_cache} by hand"
                ) from e
        digest = _sha256(cached)
        if pin:
            if mod.get("sha256") != digest:
                pinned[mod["file"]] = digest
        elif mod.get("sha256") and mod["sha256"] != digest:
            raise ValueError(f"{mod['name']}: sha256 mismatch for {cached}")
        target = mods_dir / mod["file"]
        shutil.copyfile(cached, target)
        installed.append(target)
    if pinned:
        _write_pins(manifest, pinned)
    return installed


def _write_pins(manifest: Path, pinned: dict[str, str]) -> None:
    """Вписывает sha256 в манифест построчно, чтобы сохранить комментарии."""
    lines = manifest.read_text(encoding="utf-8").splitlines(keepends=True)
    current = None
    for i, line in enumerate(lines):
        m = re.match(r"\s*file:\s*(\S+)", line)
        if m:
            current = m.group(1)
            continue
        m = re.match(r"(\s*sha256:)", line)
        if m and current in pinned:
            lines[i] = f"{m.group(1)} {pinned[current]}\n"
            current = None
    manifest.write_text("".join(lines), encoding="utf-8")


def mod_versions(manifest: Path) -> dict[str, str]:
    """Возвращает версии модов из манифеста по имени мода."""
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    return {m["name"]: str(m["version"]) for m in data["mods"]}


def write_server_files(cfg: Config) -> None:
    """Пишет eula.txt и server.properties для headless-сервера стенда."""
    cfg.server_dir.mkdir(parents=True, exist_ok=True)
    (cfg.server_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    props = {
        "enable-rcon": "true",
        "rcon.port": str(cfg.rcon_port),
        "rcon.password": cfg.rcon_password,
        "server-port": "25565",
        "online-mode": "false",
        "level-name": "world",
        "level-type": "FLAT",
        "generator-settings": GENERATOR_SETTINGS,
        "spawn-monsters": "false",
        "spawn-animals": "false",
        "spawn-npcs": "false",
        "spawn-protection": "0",
        "difficulty": "0",
        "gamemode": "1",
        "generate-structures": "false",
        "allow-nether": "false",
        "view-distance": "6",
        "max-players": "4",
        "motd": "oc-agent stand",
        "snooper-enabled": "false",
    }
    text = "".join(f"{k}={v}\n" for k, v in props.items())
    (cfg.server_dir / "server.properties").write_text(text, encoding="utf-8")


TEMPLATE_COMMANDS = [
    "setworldspawn {x} {y} {z}",
    "gamerule doMobSpawning false",
    "gamerule doDaylightCycle false",
    "gamerule doFireTick false",
    "time set 6000",
    "weather clear",
]


def create_template(cfg: Config, force: bool = False) -> Path:
    """Создаёт мир первым запуском, настраивает его и копирует в world_template_dir."""
    if cfg.world_template_dir.exists() and not force:
        return cfg.world_template_dir
    if process.is_running(cfg):
        raise RuntimeError("stop the server before creating the world template")
    if cfg.world_dir.exists():
        shutil.rmtree(cfg.world_dir)
    proc = process.start_server(cfg)
    process.wait_rcon(cfg, timeout=300, proc=proc)
    x, y, z = cfg.spawn
    with Rcon(cfg.rcon_host, cfg.rcon_port, cfg.rcon_password, timeout=30) as rcon:
        for cmd in TEMPLATE_COMMANDS:
            rcon.command(cmd.format(x=x, y=y, z=z))
        rcon.command("save-all")
    process.stop_server(cfg)
    if cfg.world_template_dir.exists():
        shutil.rmtree(cfg.world_template_dir)
    shutil.copytree(cfg.world_dir, cfg.world_template_dir)
    return cfg.world_template_dir


# Настройки OpenComputers для стенда и демо, ключ и значение в OpenComputers.cfg.
# ignorePower: робот не разряжается. limitFlightHeight: робот без Angel/Hover летает выше 8 блоков.
OC_SETTINGS = {"ignorePower": "true", "limitFlightHeight": "256"}
# Internet Card по умолчанию не пускает в локальную сеть, а мост слушает 127.0.0.1.
# Правило должно стоять до "deny private": правила проверяются сверху вниз.
OC_ALLOW_RULE = '"allow ip:127.0.0.1"'


def oc_config_path(cfg: Config) -> Path:
    return cfg.server_dir / "config" / "OpenComputers.cfg"


def patch_oc_config(text: str) -> str:
    """OpenComputers.cfg с настройками стенда. Повторный вызов ничего не меняет."""
    for key, value in OC_SETTINGS.items():
        text, n = re.subn(rf"(?m)^([ \t]*{key}[ \t]*=[ \t]*)\S+[ \t]*$", rf"\g<1>{value}", text)
        if n == 0:
            raise ValueError(f"OpenComputers.cfg has no {key}, the OC version changed?")
    if OC_ALLOW_RULE not in text:
        text, n = re.subn(r'(?m)^([ \t]*)"deny private"', rf'\g<1>{OC_ALLOW_RULE},\n\g<1>"deny private"',
                          text, count=1)
        if n == 0:
            raise ValueError('OpenComputers.cfg has no "deny private" in filteringRules')
    return text


def configure_opencomputers(cfg: Config) -> bool:
    """Вписывает настройки стенда в OpenComputers.cfg. False, если конфига ещё нет.

    Конфиг создаёт сам OpenComputers при первом запуске сервера (create_template).
    Сервер читает его только при старте.
    """
    path = oc_config_path(cfg)
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    patched = patch_oc_config(text)
    if patched != text:
        path.write_text(patched, encoding="utf-8")
    return True


def setup_all(cfg: Config, pin: bool = False) -> None:
    """Полная установка: Java, Forge, моды, конфиги, шаблон мира."""
    check_java(cfg)
    print(f"java ok: {cfg.java_path}")
    jar = install_forge(cfg)
    print(f"forge ok: {jar.name}")
    mods = install_mods(cfg, cfg.mods_manifest, pin=pin)
    print("mods ok: " + ", ".join(m.name for m in mods))
    write_server_files(cfg)
    print("server files ok")
    template = create_template(cfg)
    print(f"world template ok: {template}")
    if process.is_running(cfg):
        print("server is running: stop it and run setup again to write the OpenComputers config and the map")
        return
    if configure_opencomputers(cfg):
        print(f"opencomputers config ok: {oc_config_path(cfg)}")
    else:
        print(f"opencomputers config not found at {oc_config_path(cfg)}: start the server once and run setup again")
    map_id = navmap.ensure_nav_map([cfg.world_dir, cfg.world_template_dir])
    print(f"navigation map ok: map_{map_id} (in game: /give <nick> filled_map 1 {map_id})")
