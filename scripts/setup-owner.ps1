. (Join-Path $PSScriptRoot 'common.ps1')
try {
    Write-Host 'This prints a secret setup token once. Run only on the trusted host; do not paste it into chat.'
    Invoke-Compose exec -T api python -m app.cli setup-token
} catch { Write-Error $_; exit 1 }
