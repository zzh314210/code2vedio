param([int]$Port = 8787)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts\setup_windows.ps1 first.' }
$env:PYTHONUTF8 = '1'
$env:C2V_WEB_PORT = "$Port"
$env:C2V_WEB_HOST = '127.0.0.1'
& $python -u (Join-Path $root 'web\app.py')
