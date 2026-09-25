param([string]$MinHook = (Join-Path $PSScriptRoot '..\..\..\third_party\minhook'))
$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$build = Join-Path $source 'build'
New-Item -ItemType Directory -Path $build -Force | Out-Null
$objects = @()
foreach ($file in @('buffer.c', 'hook.c', 'trampoline.c', 'hde\hde64.c')) {
    $object = Join-Path $build ('dispatch-' + [IO.Path]::GetFileNameWithoutExtension($file) + '.o')
    & gcc -O2 -Wall -c (Join-Path $MinHook ('src\' + $file)) -I (Join-Path $MinHook 'include') -o $object
    if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $file" }
    $objects += $object
}
foreach ($mode in @('dispatch', 'harness_dispatch')) {
    $flags = @()
    if ($mode -eq 'harness_dispatch') { $flags += '-DRESEARCH_HARNESS' }
    & g++ -std=c++17 -O2 -Wall -Wextra -Werror -shared -static-libgcc -static-libstdc++ @flags (Join-Path $source 'dispatch.cpp') @objects -I (Join-Path $MinHook 'include') -o (Join-Path $build ($mode + '.dll'))
    if ($LASTEXITCODE -ne 0) { throw "Link failed: $mode" }
}
