. (Join-Path $PSScriptRoot 'common.ps1')
Invoke-Compose exec -T api python -m app.cli seed
