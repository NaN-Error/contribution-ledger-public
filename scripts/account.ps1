param(
    [Parameter(Mandatory=$true)][ValidateSet('recover','disable','enable')][string]$Action,
    [Parameter(Mandatory=$true)][string]$Email,
    [Parameter(Mandatory=$true)][ValidateLength(8,500)][string]$Reason
)
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    Write-Host 'Operator action: verify the account owner and your authority before continuing.'
    $confirmation = Read-Host "Type the account email to confirm $Action"
    if ($confirmation -cne $Email) { Write-Host 'Cancelled; no account change performed.'; exit 0 }
    Invoke-Compose exec -T api python -m app.cli "$Action-account" --email "$Email" --reason "$Reason"
} catch { Write-Error $_; exit 1 }
