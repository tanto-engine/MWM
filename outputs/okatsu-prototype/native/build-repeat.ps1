# Compatibility build entry point. Production compilation has one maintained path.
param(
    [ValidatePattern('^boss_repeat_[0-9a-f]{16}$')]
    [string]$OutputName,
    [string]$MinHook = (Join-Path $PSScriptRoot '..\..\..\third_party\minhook')
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'build-runtime.ps1') -MinHook $MinHook
if ($OutputName) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'build\nioh_skill_runtime.dll') `
        -Destination (Join-Path $PSScriptRoot ('build\' + $OutputName + '.dll'))
}
