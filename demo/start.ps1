# Поднимает всё, что должно работать до запуска Claude Code:
#   1. сервер Minecraft стенда (localhost:25565, RCON 25575);
#   2. раздачу Lua-скриптов oc-mcp роботу (http://127.0.0.1:8770) в отдельном окне.
# Флаг -Reset заново ставит площадку и склад (робот в регионе при этом удаляется!).
param([switch]$Reset)

$ErrorActionPreference = "Stop"
$play = $PSScriptRoot
$root = Join-Path $play ".." | Resolve-Path
$py = Join-Path $root ".venv\Scripts\python.exe"

Push-Location $root
try {
    & $py -m stand.server start
    if ($LASTEXITCODE -ne 0) { throw "server did not start" }
    if ($Reset) {
        & $py -m stand.runner prepare --scenario (Join-Path $play "scenario.yaml")
        if ($LASTEXITCODE -ne 0) { throw "prepare failed" }
    }
} finally { Pop-Location }

$serving = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like '*serve_lua.py*' }
if (-not $serving) {
    Start-Process -FilePath $py -ArgumentList (Join-Path $play "serve_lua.py") -WorkingDirectory $play
    Write-Host "lua server: http://127.0.0.1:8770 (separate window)"
} else {
    Write-Host "lua server already running"
}
Write-Host "minecraft server: localhost:25565"
