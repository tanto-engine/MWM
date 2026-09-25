param(
    [string]$Python = 'python',
    [string]$DownloadsCopy = (Join-Path $env:USERPROFILE 'Downloads\Nioh1-Sword-Move-Observations.xlsx')
)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    & $Python -c 'import sys; from catalogue.spreadsheet_sync import sync_workbook; print("Synchronized:", *sync_workbook(downloads_copy=sys.argv[1]), sep="\n")' $DownloadsCopy
    if ($LASTEXITCODE -ne 0) { throw "Catalogue synchronization failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}
