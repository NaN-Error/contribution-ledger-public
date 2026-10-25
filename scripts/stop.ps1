. (Join-Path $PSScriptRoot 'common.ps1')
# Never pass --volumes/-v. Named PostgreSQL data is preserved.
Stop-OptionalIntegrations
Invoke-Compose down --remove-orphans
Write-Host 'Services stopped. Named database storage and .env have been preserved.'
