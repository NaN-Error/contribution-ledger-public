. (Join-Path $PSScriptRoot 'common.ps1')
Write-Host 'This deletes only the synthetic phase-1 persistence marker. Application data and schema are not reset.'
$confirmation = Read-Host 'Type DELETE DEVELOPMENT RECORDS to proceed'
if ($confirmation -cne 'DELETE DEVELOPMENT RECORDS') { Write-Host 'Cancelled. No data was changed.'; return }
Invoke-Compose exec -T api python -m app.cli reset-development --confirm $confirmation
