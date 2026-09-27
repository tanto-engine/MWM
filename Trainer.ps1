# Open MWM's Electron interface, or explicitly request its Enable/Disable lifecycle command.
# LegacyUI preserves the old trainer for comparison; each launcher mode is mutually exclusive.
# This development launcher does not compile an EXE or bypass Build.ps1 release controls.
param(
    [string]$PythonRuntime = $env:NIOH_PYTHON,
    [switch]$Enable,
    [switch]$Disable,
    [switch]$LegacyUI
)
$ErrorActionPreference = 'Stop'
if (([int]$Enable.IsPresent + [int]$Disable.IsPresent + [int]$LegacyUI.IsPresent) -gt 1) { throw 'Choose one launcher mode.' }
$scriptPath = Join-Path $PSScriptRoot 'launch.py'
# Control commands return a checked exit status; ordinary UI launch uses a hidden console.
if ($Enable -or $Disable) {
    if (-not $PythonRuntime) { $PythonRuntime = 'python.exe' }
    $mode = if ($Enable) { '--enable' } else { '--disable' }
    & $PythonRuntime -B $scriptPath $mode
    if ($LASTEXITCODE -ne 0) { throw "Runtime control failed: $LASTEXITCODE" }
} elseif ($LegacyUI) {
    if (-not $PythonRuntime) { $PythonRuntime = 'python.exe' }
    Start-Process -FilePath $PythonRuntime -ArgumentList @('-B', ('"' + $scriptPath + '"'), '--legacy-ui') -WindowStyle Hidden
} else {
    # Compile local UI sources before launch so authored changes cannot leave stale JavaScript visible.
    # npm ci is an explicit development prerequisite; this path never invokes electron-builder or makes an EXE.
    # The child inherits an optional Python override, which is restored in this shell immediately afterward.
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'node_modules'))) { throw 'Run npm ci in MWM before launching the desktop UI.' }
    # Source testing must use the current native code, not a DLL left by a previous release.
    # Build only the Engine DLLs; opening this editor still performs no game attachment.
    # Enable copies the completed libraries into its immutable session before using them.
    & (Join-Path $PSScriptRoot '..\tanto-engine\runtime\native\Build.ps1')
    Push-Location $PSScriptRoot
    try {
        & npm.cmd run build:ui
        if ($LASTEXITCODE -ne 0) { throw 'MWM UI compilation failed.' }
    } finally { Pop-Location }
    $previousPython = $env:NIOH_PYTHON
    try {
        if ($PythonRuntime) { $env:NIOH_PYTHON = $PythonRuntime }
        # Electron's CLI also resolves its local binary on a fresh npm installation.
        $electronCli = Join-Path $PSScriptRoot 'node_modules\electron\cli.js'
        Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @(('"' + $electronCli + '"'), ('"' + $PSScriptRoot + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
    } finally { $env:NIOH_PYTHON = $previousPython }
}
