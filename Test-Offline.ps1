param(
    [string]$PythonRuntime = 'python',
    [string]$Cxx = 'g++'
)
$ErrorActionPreference = 'Stop'
$previousCxx = $env:CXX
$env:CXX = $Cxx
Push-Location -LiteralPath $PSScriptRoot
try {
    & $PythonRuntime -B tests/test_move_readiness.py --offline
    if ($LASTEXITCODE -ne 0) { throw 'Offline move checks failed.' }
    & $PythonRuntime -B tests/test_resource_crashes.py
    if ($LASTEXITCODE -ne 0) { throw 'Resource crash regression failed.' }
} finally {
    Pop-Location
    $env:CXX = $previousCxx
}
