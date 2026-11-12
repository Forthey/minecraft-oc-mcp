# Выдаёт игроку op, карту map_0 (масштаб 1, центр 0,0) и ванильные ингредиенты Navigation Upgrade.
#   .\give_map.ps1 -Nick <ник в игре>      (игрок должен быть онлайн)
# Рецепт: золото, компас, золото / Microchip T2, карта, Microchip T2 / золото, зелье (бутылка воды), золото.
# Microchip (Tier 2) возьмите в творческой вкладке OpenComputers.
param([Parameter(Mandatory = $true)][string]$Nick)

$root = Join-Path $PSScriptRoot ".." | Resolve-Path
$code = @"
from stand.rcon import Rcon
with Rcon('127.0.0.1', 25575, 'stand-rcon', timeout=10) as r:
    for cmd in ['op $Nick', 'give $Nick filled_map 1 0', 'give $Nick gold_ingot 4',
                'give $Nick compass 1', 'give $Nick potion 1 0', 'give $Nick crafting_table 1']:
        print(r.command(cmd))
"@
Push-Location $root
try { & (Join-Path $root ".venv\Scripts\python.exe") -c $code } finally { Pop-Location }
