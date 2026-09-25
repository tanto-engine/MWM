param([string]$PythonRuntime = 'python.exe')
$ErrorActionPreference = 'Stop'
Start-Process -FilePath $PythonRuntime -ArgumentList @('-B', ('"' + (Join-Path $PSScriptRoot 'outputs\okatsu-prototype\trainer.py') + '"')) -WindowStyle Hidden
