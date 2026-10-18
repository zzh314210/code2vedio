param([string]$CacheRoot='D:\Code2VideoCache',[switch]$Start)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$basePython=Join-Path $projectRoot '.venv\Scripts\python.exe'
$speechRoot=Join-Path $CacheRoot 'tts'
$repo=Join-Path $speechRoot 'GPT-SoVITS'
$speechPython=Join-Path $speechRoot 'venv-cpu\Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $speechRoot | Out-Null
if(-not(Test-Path -LiteralPath $repo)){
 & git -c http.proxy= -c https.proxy= clone https://github.com/RVC-Boss/GPT-SoVITS.git $repo
 if($LASTEXITCODE -ne 0){throw 'GPT-SoVITS clone failed'}
 & git -c "safe.directory=$repo" -C $repo checkout 1b47ca07ef43a284e0b8bd7f29d3e1e3ff76082a
 if($LASTEXITCODE -ne 0){throw 'Unable to pin upstream commit'}
}
if(-not(Test-Path -LiteralPath $speechPython)){
 & $basePython -m venv (Join-Path $speechRoot 'venv-cpu')
 if($LASTEXITCODE -ne 0){throw 'CPU venv creation failed'}
}
& $speechPython -m pip install -r (Join-Path $projectRoot 'requirements-speech-cpu.txt')
if($LASTEXITCODE -ne 0){throw 'CPU dependencies installation failed'}
& $basePython (Join-Path $PSScriptRoot 'download_speech_models.py') $repo
if($LASTEXITCODE -ne 0){throw 'Speech model download failed'}
& $basePython (Join-Path $PSScriptRoot 'download_whisper_model.py') (Join-Path $CacheRoot 'asr\faster-whisper-small')
if($LASTEXITCODE -ne 0){throw 'Whisper model download failed'}
if($Start){
 & $speechPython -u (Join-Path $PSScriptRoot 'run_sovits_cpu.py') $repo
}
