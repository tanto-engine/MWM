param(
    [string]$PythonRuntime = '',
    [string]$Cxx = ''
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not $PythonRuntime) {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) { $PythonRuntime = $python.Source }
    else { $PythonRuntime = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' }
}
if (-not (Test-Path -LiteralPath $PythonRuntime)) { throw 'Pass -PythonRuntime with a 64-bit Python executable.' }
if (-not $Cxx) {
    $compiler = Get-Command g++.exe -ErrorAction SilentlyContinue
    if ($compiler) { $Cxx = $compiler.Source }
    else { $Cxx = Join-Path $env:USERPROFILE 'scoop\apps\gcc\current\bin\g++.exe' }
    if (-not (Test-Path -LiteralPath $Cxx)) { $Cxx = Join-Path $env:LOCALAPPDATA 'Scoop\apps\gcc\current\bin\g++.exe' }
}
if (-not (Test-Path -LiteralPath $Cxx)) { throw 'Install GCC/G++ on PATH or pass -Cxx with g++.exe.' }
$tests = Join-Path $root 'work\native-tests'
$build = Join-Path $tests 'build'
$include = Join-Path $root 'third_party\minhook\include'
if (-not (Test-Path -LiteralPath (Join-Path $include 'MinHook.h'))) { throw 'Missing third_party/minhook/include/MinHook.h.' }
$sessionHeader = Join-Path $root 'outputs\okatsu-prototype\native\boss_session.h'
if (-not (Test-Path -LiteralPath $sessionHeader)) {
    [IO.File]::Copy((Join-Path $tests 'fixtures\boss_session.stub.h'), $sessionHeader, $false)
}
New-Item -ItemType Directory -Path $build -Force | Out-Null
Push-Location $root
try {
    & $PythonRuntime -B -c 'import ctypes; assert ctypes.sizeof(ctypes.c_void_p) == 8, "Require 64-bit Python"'
    if ($LASTEXITCODE -ne 0) { throw 'Python architecture check failed.' }
    $pythonTests = @(
        Get-ChildItem -LiteralPath (Join-Path $root 'work') -Filter 'test_*.py' -File
        Get-Item -LiteralPath (Join-Path $root 'work\controller_reader_test.py')
        Get-ChildItem -LiteralPath $tests -Filter 'test_*.py' -File
    ) | Sort-Object FullName
    foreach ($test in $pythonTests) {
        Write-Output ('Testing ' + $test.Name)
        & $PythonRuntime -B $test.FullName
        if ($LASTEXITCODE -ne 0) { throw "Python test failed: $($test.Name)" }
    }
    $nativeTests = Get-ChildItem -LiteralPath $tests -Filter 'test_*.cpp' -File | Sort-Object Name
    foreach ($test in $nativeTests) {
        $executable = Join-Path $build ($test.BaseName + '.exe')
        Write-Output ('Building and testing ' + $test.Name)
        & $Cxx -std=c++17 -O2 -Wall -Wextra -Werror -static-libgcc -static-libstdc++ $test.FullName -I $include -o $executable
        if ($LASTEXITCODE -ne 0) { throw "Native test build failed: $($test.Name)" }
        if ($test.BaseName -eq 'test_publisher_protocol') {
            & $executable (Join-Path $tests 'publisher-command.bin')
        } else { & $executable }
        if ($LASTEXITCODE -ne 0) { throw "Native test failed: $($test.Name)" }
    }
    Write-Output "Offline checks passed: $($pythonTests.Count) Python test files and $($nativeTests.Count) native test programs. No game/controller access or DLL loading performed."
} finally { Pop-Location }
