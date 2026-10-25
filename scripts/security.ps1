param([ValidateSet('init','status')][string]$Action='status')
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    if ($Action -eq 'init') {
        Stop-OptionalIntegrations
        Invoke-Compose stop api web
        Invoke-Compose build api migrate security-init
        Invoke-Compose up -d --wait --wait-timeout 120 db
        Invoke-Compose run --rm --no-deps migrate
        Invoke-Compose run --rm --no-deps security-init
        Write-Host 'Authentication master initialized or verified without replacement. Recreate the API to mount auth_master, then enroll in Account and sessions.'
    } else { Invoke-Compose ps }
} catch { Write-Error $_; exit 1 }
