param(
    [string]$Mirror = 'https://pypi.tuna.tsinghua.edu.cn/simple',
    [string]$NpmMirror = 'https://registry.npmmirror.com',
    [switch]$WithGraphics
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & py -3.12 -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 (64-bit) first.' }
}
& $python -m pip config --site set global.index-url $Mirror
& $python -m pip config --site set global.timeout 120
& $python -m pip install --upgrade pip --index-url $Mirror
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $python -m pip install -r (Join-Path $root 'src\requirements.txt') --index-url $Mirror
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Try -Mirror https://mirrors.aliyun.com/pypi/simple/' }
if ($WithGraphics) {
    Push-Location (Join-Path $root 'tools\graphics')
    try {
        & npm.cmd install --registry=$NpmMirror --ignore-scripts
        if ($LASTEXITCODE -ne 0) { throw 'Graphics bridge installation failed.' }
    } finally { Pop-Location }
}
$local = Join-Path $root 'config.local.json'
if (-not (Test-Path -LiteralPath $local)) { Copy-Item -LiteralPath (Join-Path $root 'config.example.json') -Destination $local }
$env:PYTHONUTF8 = '1'
& $python (Join-Path $root 'src\agent.py') --doctor
if ($LASTEXITCODE -ne 0) { throw 'Environment check failed.' }
Write-Output 'Ready. Run src\agent.py --help for CLI options.'
