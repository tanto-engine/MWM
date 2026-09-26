param(
    [string]$PythonRuntime = $env:NIOH_PYTHON,
    [switch]$Enable,
    [switch]$Disable
)
$ErrorActionPreference = 'Stop'
if ($Enable -and $Disable) { throw 'Choose either -Enable or -Disable.' }
if (-not $PythonRuntime) { $PythonRuntime = 'python.exe' }
$scriptPath = Join-Path $PSScriptRoot 'launch.py'
if ($Enable -or $Disable) {
    $mode = if ($Enable) { '--enable' } else { '--disable' }
    & $PythonRuntime -B $scriptPath $mode
    if ($LASTEXITCODE -ne 0) { throw "Runtime control failed: $LASTEXITCODE" }
} else {
    Start-Process -FilePath $PythonRuntime -ArgumentList @('-B', ('"' + $scriptPath + '"')) -WindowStyle Hidden
}
