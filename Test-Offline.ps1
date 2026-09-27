# Run both maintained offline suites from the repository root, regardless of the calling directory.
# Pass the selected C++ compiler through CXX so native fixtures use the same toolchain as the Python checks.
# Always restore the caller's directory and CXX value, including when a suite reports a nonzero exit.
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
