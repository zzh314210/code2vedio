param([switch]$NoBrowser, [switch]$Install)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $root '.venv\Scripts\python.exe'
$web = Join-Path $root 'web'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
if ($Install) {
    # A fresh Studio checkout uses the Alibaba template; the generic CLI
    # setup must not create its OpenAI/Edge defaults first.
    $localConfig = Join-Path $root 'config.local.json'
    if (-not (Test-Path -LiteralPath $localConfig)) {
        Copy-Item -LiteralPath (Join-Path $root 'config.studio.example.json') -Destination $localConfig
    }
    & (Join-Path $PSScriptRoot 'setup_windows.ps1') -Mirror 'https://pypi.org/simple'
    if ($LASTEXITCODE -ne 0) { throw 'Python setup failed.' }
    Push-Location $web
    try {
        & npm.cmd ci --registry=https://registry.npmjs.org
        if ($LASTEXITCODE -ne 0) { throw 'UI dependency installation failed.' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'UI build failed.' }
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts\start_studio.ps1 -Install first.' }
if (-not (Test-Path -LiteralPath (Join-Path $web 'dist\index.html'))) { throw 'Build the UI: cd web; npm ci; npm run build' }
if (Test-Path -LiteralPath (Join-Path $root 'config.gpt-sovits.local.json')) {
    try { & (Join-Path $PSScriptRoot 'start_speech.ps1') } catch { Write-Warning $_.Exception.Message }
}
$url = 'http://127.0.0.1:7860'
$ready = $false
try { $null = Invoke-RestMethod "$url/api/config" -TimeoutSec 2; $ready = $true } catch { }
if (-not $ready) {
    $logs = Join-Path $root '.tmp'
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    $server = Join-Path $web 'server.py'
    $null = Start-Process -FilePath $python -ArgumentList @('-u', ('"' + $server + '"')) -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'studio-server.out.log') -RedirectStandardError (Join-Path $logs 'studio-server.err.log') -PassThru
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try { $null = Invoke-RestMethod "$url/api/config" -TimeoutSec 2; $ready = $true; break } catch { }
    }
}
if (-not $ready) { throw 'Server did not start. Check .tmp\studio-server.err.log' }
if (-not $NoBrowser) { Start-Process $url }
Write-Output "Frame Studio: $url"
