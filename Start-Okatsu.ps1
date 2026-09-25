param([string]$PythonRuntime, [string]$MinHook)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'outputs\okatsu-prototype\Start-Okatsu.ps1') @PSBoundParameters
