# Compile bundled MinHook as C, then link the production runtime and resource loader as separate x64 DLLs.
# The runtime translation unit includes observer.cpp with production feature switches; do not compile it twice.
# Outputs stay under native/build; building performs no injection, controller sampling or game-process lookup.
param([string]$MinHook = (Join-Path $PSScriptRoot '..\..\third_party\minhook'))
$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$build = Join-Path $source 'build'
New-Item -ItemType Directory -Path $build -Force | Out-Null
$objects = @()
foreach ($file in @('buffer.c', 'hook.c', 'trampoline.c', 'hde\hde64.c')) {
    $object = Join-Path $build ('runtime-' + [IO.Path]::GetFileNameWithoutExtension($file) + '.o')
    & gcc -O2 -Wall -c (Join-Path $MinHook ('src\' + $file)) -I (Join-Path $MinHook 'include') -o $object
    if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $file" }
    $objects += $object
}
# Identical source rebuilds retain identical DLL hashes; only changed native code requires a new game process.
& g++ -std=c++17 -O2 -Wall -Wextra -Werror -shared -static-libgcc -static-libstdc++ '-Wl,--no-insert-timestamp' `
    (Join-Path $source 'runtime.cpp') @objects -I (Join-Path $MinHook 'include') `
    -o (Join-Path $build 'nioh_skill_runtime.dll')
if ($LASTEXITCODE -ne 0) { throw 'Link failed: nioh_skill_runtime.dll' }
Write-Output 'Built nioh_skill_runtime.dll. Session data is supplied at startup; no game access performed.'
& g++ -std=c++17 -O2 -Wall -Wextra -Werror -shared -static-libgcc -static-libstdc++ '-Wl,--no-insert-timestamp' `
    (Join-Path $source 'resource_loader.cpp') @objects -I (Join-Path $MinHook 'include') `
    -o (Join-Path $build 'nioh_resources.dll')
if ($LASTEXITCODE -ne 0) { throw 'Link failed: nioh_resources.dll' }
