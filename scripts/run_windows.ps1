param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:PYTHONUTF8 = '1'
& (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'src\agent.py') @Arguments
exit $LASTEXITCODE
