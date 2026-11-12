# Останавливает сервер Minecraft стенда и раздачу Lua.
$play = $PSScriptRoot
$root = Join-Path $play ".." | Resolve-Path
Push-Location $root
try { & (Join-Path $root ".venv\Scripts\python.exe") -m stand.server stop } finally { Pop-Location }
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like '*serve_lua.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
