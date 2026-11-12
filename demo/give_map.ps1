# Выдаёт игроку op, карту стенда (масштаб 1, центр 0,0, её пишет stand.server setup) и ванильные ингредиенты Navigation Upgrade.
#   .\give_map.ps1 -Nick <ник в игре>      (игрок должен быть онлайн)
# Рецепт: золото, компас, золото / Microchip T2, карта, Microchip T2 / золото, зелье (бутылка воды), золото.
# Microchip (Tier 2) возьмите в творческой вкладке OpenComputers.
param([Parameter(Mandatory = $true)][string]$Nick)

$root = Join-Path $PSScriptRoot ".." | Resolve-Path
$code = @"
from stand.config import load_config
from stand.rcon import Rcon
from stand.server.navmap import find_nav_map
cfg = load_config()
map_id = find_nav_map(cfg.world_dir)
if map_id is None:
    raise SystemExit('no navigation map in the world: stop the server and run: uv run python -m stand.server setup')
with Rcon(cfg.rcon_host, cfg.rcon_port, cfg.rcon_password, timeout=10) as r:
    for cmd in ['op $Nick', f'give $Nick filled_map 1 {map_id}', 'give $Nick gold_ingot 4',
                'give $Nick compass 1', 'give $Nick potion 1 0', 'give $Nick crafting_table 1']:
        print(r.command(cmd))
"@
Push-Location $root
try { & (Join-Path $root ".venv\Scripts\python.exe") -c $code } finally { Pop-Location }
