. (Join-Path $PSScriptRoot 'common.ps1')
try {
    Write-Host 'Optional synthetic accounts only. Random passwords will appear once in this terminal.'
    $confirmation = Read-Host 'Type CREATE SYNTHETIC TEAM to continue'
    if ($confirmation -cne 'CREATE SYNTHETIC TEAM') { Write-Host 'Cancelled.'; exit 0 }
    Invoke-Compose exec -T api python -m app.cli seed-team --confirm "$confirmation"
} catch { Write-Error $_; exit 1 }
