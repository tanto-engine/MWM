$ErrorActionPreference = 'Stop'
'stop' | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'stop.flag')
Write-Output 'Stop requested. The controller will disarm immediately and let any active move restore the player resources. No process is terminated.'
