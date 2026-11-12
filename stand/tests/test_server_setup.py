import hashlib
import subprocess
from dataclasses import replace

import pytest
import yaml

from stand.config import load_config
from stand.server import setup


@pytest.fixture
def cfg(tmp_path):
    base = load_config()
    return replace(
        base,
        server_dir=tmp_path / "instance",
        mods_cache=tmp_path / "cache",
        world_template_dir=tmp_path / "template",
        rcon_password="secret",
    )


def _props(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k] = v
    return out


def test_server_properties(cfg):
    setup.write_server_files(cfg)
    assert (cfg.server_dir / "eula.txt").read_text(encoding="utf-8").strip().endswith("eula=true")
    props = _props(cfg.server_dir / "server.properties")
    expected = {
        "enable-rcon": "true",
        "rcon.port": "25575",
        "rcon.password": "secret",
        "online-mode": "false",
        "level-type": "FLAT",
        "generator-settings": "2;7,59x1,3x3,2;1;",
        "spawn-monsters": "false",
        "spawn-animals": "false",
        "spawn-npcs": "false",
        "spawn-protection": "0",
        "difficulty": "0",
        "gamemode": "1",
        "generate-structures": "false",
    }
    for key, value in expected.items():
        assert props[key] == value, key


@pytest.mark.parametrize(
    "output,major",
    [
        ('openjdk version "1.8.0_402"\nOpenJDK Runtime Environment', 8),
        ('openjdk version "25.0.5" 2026-10-24', 25),
        ('java version "1.8.0_202"', 8),
    ],
)
def test_java_major_parses(monkeypatch, output, major):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="", stderr=output)

    monkeypatch.setattr(setup.subprocess, "run", fake_run)
    assert setup.java_major("java") == major


def _manifest(tmp_path, data, sha):
    path = tmp_path / "mods.yaml"
    path.write_text(
        yaml.safe_dump({"forge": "x", "mods": [
            {"name": "demo", "version": "1", "file": "demo.jar", "url": None, "sha256": sha}
        ]}),
        encoding="utf-8",
    )
    return path


def test_install_mods_uses_cache_and_checks_sha(cfg, tmp_path):
    data = b"jar-bytes"
    cfg.mods_cache.mkdir(parents=True)
    (cfg.mods_cache / "demo.jar").write_bytes(data)

    good = _manifest(tmp_path, data, hashlib.sha256(data).hexdigest())
    setup.install_mods(cfg, good)
    assert (cfg.server_dir / "mods" / "demo.jar").read_bytes() == data

    bad = _manifest(tmp_path, data, "0" * 64)
    with pytest.raises(ValueError, match="demo"):
        setup.install_mods(cfg, bad)


def test_install_mods_removes_jars_not_in_manifest(cfg, tmp_path):
    # Старая версия мода рядом с новой роняет Forge на дубликате. Подпапки (mods/1.7.10
    # с библиотеками CodeChickenCore) не трогаются.
    data = b"jar-bytes"
    cfg.mods_cache.mkdir(parents=True)
    (cfg.mods_cache / "demo.jar").write_bytes(data)
    mods_dir = cfg.server_dir / "mods"
    (mods_dir / "1.7.10").mkdir(parents=True)
    (mods_dir / "old-version.jar").write_bytes(b"old")
    (mods_dir / "1.7.10" / "lib.jar").write_bytes(b"lib")
    setup.install_mods(cfg, _manifest(tmp_path, data, hashlib.sha256(data).hexdigest()))
    assert sorted(p.name for p in mods_dir.glob("*.jar")) == ["demo.jar"]
    assert (mods_dir / "1.7.10" / "lib.jar").exists()


def test_install_mods_missing_without_url_explains(cfg, tmp_path):
    manifest = _manifest(tmp_path, b"", None)
    with pytest.raises(FileNotFoundError, match="mods-cache|demo.jar"):
        setup.install_mods(cfg, manifest)


def test_pin_keeps_comments(cfg, tmp_path):
    data = b"jar-bytes"
    cfg.mods_cache.mkdir(parents=True)
    (cfg.mods_cache / "demo.jar").write_bytes(data)
    manifest = tmp_path / "mods.yaml"
    manifest.write_text(
        "# comment stays\nforge: x\nmods:\n  - name: demo\n    version: '1'\n"
        "    file: demo.jar\n    url: null\n    sha256: null\n",
        encoding="utf-8",
    )
    setup.install_mods(cfg, manifest, pin=True)
    text = manifest.read_text(encoding="utf-8")
    assert text.startswith("# comment stays")
    assert yaml.safe_load(text)["mods"][0]["sha256"] == hashlib.sha256(data).hexdigest()


def test_wait_rcon_notices_dead_process(cfg):
    import sys
    import time

    from stand.rcon import RconError
    from stand.server import process

    cfg = replace(cfg, rcon_port=1)
    cfg.server_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    start = time.monotonic()
    with pytest.raises(RconError, match="exited"):
        process.wait_rcon(cfg, timeout=30, proc=proc)
    assert time.monotonic() - start < 10


def test_pid_alive_false_for_exited_child():
    import sys

    from stand.server import process

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    import time
    time.sleep(1)
    assert process._pid_alive(proc.pid) is False


# Фрагмент OpenComputers.cfg 1.8.10 в исходном виде.
OC_CFG = """\
  internet {
    filteringRules=[
      removeme,
      "deny private",
      "deny bogon",
      "allow default"
    ]
  }
  power {
    ignorePower=false

    # comment
  }
  robot {
    limitFlightHeight=8
  }
"""


def test_patch_oc_config():
    out = setup.patch_oc_config(OC_CFG)
    lines = [line.strip() for line in out.splitlines()]
    assert lines.index('"allow ip:127.0.0.1",') == lines.index('"deny private",') - 1
    assert "ignorePower=true" in lines and "limitFlightHeight=256" in lines
    assert "\n    ignorePower=true\n\n    # comment\n" in out
    assert setup.patch_oc_config(out) == out


def test_configure_opencomputers(cfg):
    assert setup.configure_opencomputers(cfg) is False
    path = setup.oc_config_path(cfg)
    path.parent.mkdir(parents=True)
    path.write_text(OC_CFG, encoding="utf-8")
    assert setup.configure_opencomputers(cfg) is True
    assert "ignorePower=true" in path.read_text(encoding="utf-8")


def test_ensure_nav_map(tmp_path):
    from stand.server.navmap import ensure_nav_map, find_nav_map
    from stand.world.nbt import TagShort, write_nbt

    world, template = tmp_path / "world", tmp_path / "template"
    (world / "data").mkdir(parents=True)
    template.mkdir()
    # В мире уже есть чужая карта 0: карта стенда получает id 1.
    (world / "data" / "map_0.dat").write_bytes(write_nbt({"data": {"scale": 3, "xCenter": 500, "zCenter": 0}}))
    (world / "data" / "idcounts.dat").write_bytes(write_nbt({"map": TagShort(0)}, "none"))
    assert ensure_nav_map([world, template]) == 1
    assert find_nav_map(world) == find_nav_map(template) == 1
    assert ensure_nav_map([world, template]) == 1
    assert sorted(p.name for p in (world / "data").glob("map_*.dat")) == ["map_0.dat", "map_1.dat"]
