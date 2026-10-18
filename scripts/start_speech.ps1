param([string]$CacheRoot='D:\Code2VideoCache')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$repo=Join-Path $CacheRoot 'tts\GPT-SoVITS'
$speechPython=Join-Path $CacheRoot 'tts\venv-cpu\Scripts\python.exe'
try {
    $null=Invoke-RestMethod 'http://127.0.0.1:9880/openapi.json' -TimeoutSec 2
    Write-Output 'Local male-teacher speech service is ready: http://127.0.0.1:9880'
    return
} catch { }
if (Get-NetTCPConnection -LocalPort 9880 -State Listen -ErrorAction SilentlyContinue) {
    Write-Output 'Speech service is starting on port 9880.'
    return
}
if (-not(Test-Path -LiteralPath $speechPython) -or -not(Test-Path -LiteralPath (Join-Path $repo 'cpu-infer.yaml'))) {
    throw 'Run scripts\setup_local_speech.ps1 first; CPU speech installation is missing.'
}
$logs=Join-Path $projectRoot '.tmp'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$launcher=Join-Path $PSScriptRoot 'run_sovits_cpu.py'
$arguments=@('-X','faulthandler','-u',('"'+$launcher+'"'),('"'+$repo+'"'))
$null=Start-Process -FilePath $speechPython -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'speech-cpu.out.log') -RedirectStandardError (Join-Path $logs 'speech-cpu.err.log') -PassThru
Write-Output 'Local male-teacher service starting on CPU; see .tmp/speech-cpu.err.log.'
