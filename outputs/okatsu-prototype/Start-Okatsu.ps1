param(
    [string]$PythonRuntime = $env:NIOH_PYTHON,
    [string]$MinHook = (Join-Path $PSScriptRoot '..\..\third_party\minhook')
)
$ErrorActionPreference = 'Stop'
$folder = $PSScriptRoot
$statePath = Join-Path $folder 'play-process.json'
$previous = $null
if (Test-Path -LiteralPath $statePath) {
    $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $existing = Get-Process -Id $previous.publisher_pid -ErrorAction SilentlyContinue
    if ($existing -and $existing.StartTime.ToFileTimeUtc().ToString() -eq $previous.publisher_start_filetime) {
        Write-Output 'Skill runtime is already running. Check play-status.json and controller-binding.json for the active preset.'
        return
    }
}
if (-not $PythonRuntime) {
    foreach ($name in @('python.exe', 'python3.exe', 'py.exe')) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) { continue }
        $probe = @('-c', "import struct,sys; sys.exit(1) if struct.calcsize('P') != 8 else print(sys.executable)")
        if ($name -eq 'py.exe') { $probe = @('-3') + $probe }
        try { $detected = & $command.Source @probe 2>$null } catch { continue }
        if ($LASTEXITCODE -eq 0 -and $detected -and (Test-Path -LiteralPath ([string]$detected))) {
            $PythonRuntime = [string]$detected
            break
        }
    }
    if (-not $PythonRuntime) {
        $PythonRuntime = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    }
}
if (-not (Test-Path -LiteralPath $PythonRuntime)) {
    $command = Get-Command $PythonRuntime -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { $PythonRuntime = $command.Source }
}
if (-not (Test-Path -LiteralPath $PythonRuntime)) { throw '64-bit Python is missing; pass -PythonRuntime or set NIOH_PYTHON.' }
$PythonRuntime = (Resolve-Path -LiteralPath $PythonRuntime).Path
if (-not (Test-Path -LiteralPath (Join-Path $folder 'native\build\nioh_skill_runtime.dll'))) { throw 'Prebuilt runtime is missing. Run outputs\okatsu-prototype\native\build-runtime.ps1 once as a developer.' }
if (-not (Test-Path -LiteralPath (Join-Path $folder 'controller-calibration.json'))) { throw 'Saved controller calibration is missing.' }

$stopFile = Join-Path $folder 'stop.flag'
if (Test-Path -LiteralPath $stopFile) { Remove-Item -LiteralPath $stopFile }
$runFolder = Join-Path $folder ('sessions\launcher-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $runFolder -Force | Out-Null
$stdout = Join-Path $runFolder 'stdout.txt'
$stderr = Join-Path $runFolder 'stderr.txt'
$arguments = @('-B', ('"' + (Join-Path $folder 'play_okatsu.py') + '"'))
$publisher = Start-Process -FilePath $PythonRuntime -ArgumentList $arguments -WorkingDirectory $folder `
    -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
@{ publisher_pid=$publisher.Id; publisher_start_filetime=$publisher.StartTime.ToFileTimeUtc().ToString();
   stdout=$stdout; stderr=$stderr } | ConvertTo-Json | Set-Content -LiteralPath $statePath
Write-Output 'Okatsu launcher started. Check play-status.json for enabled/waiting status. Run Stop-Okatsu.ps1 to disable.'
