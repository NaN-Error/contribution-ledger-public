param([ValidateSet('api','db','web')][string]$Service = 'api')
. (Join-Path $PSScriptRoot 'common.ps1')
Invoke-Compose logs --tail 150 --follow $Service
