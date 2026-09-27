# Launch MWM from source, or explicitly request its Enable/Disable lifecycle command.
# Enable and Disable are mutually exclusive; launch.py selects source or packaged worker paths.
# This development launcher does not compile an EXE or bypass Build.ps1 release controls.
param(
    [string]$PythonRuntime = $env:NIOH_PYTHON,
    [switch]$Enable,
    [switch]$Disable
)
$ErrorActionPreference = 'Stop'
if ($Enable -and $Disable) { throw 'Choose either -Enable or -Disable.' }
if (-not $PythonRuntime) { $PythonRuntime = 'python.exe' }
$scriptPath = Join-Path $PSScriptRoot 'launch.py'
# Control commands return a checked exit status; ordinary UI launch uses a hidden console.
if ($Enable -or $Disable) {
    $mode = if ($Enable) { '--enable' } else { '--disable' }
    & $PythonRuntime -B $scriptPath $mode
    if ($LASTEXITCODE -ne 0) { throw "Runtime control failed: $LASTEXITCODE" }
} else {
    Start-Process -FilePath $PythonRuntime -ArgumentList @('-B', ('"' + $scriptPath + '"')) -WindowStyle Hidden
}
