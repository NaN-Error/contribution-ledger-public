Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:ProjectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    Push-Location $script:ProjectRoot
    try {
        & docker compose --project-directory $script:ProjectRoot -f (Join-Path $script:ProjectRoot 'compose.yaml') @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed (exit $LASTEXITCODE). Inspect service status and logs; do not delete database volumes." }
    } finally { Pop-Location }
}

function Get-LocalSetting {
    param([string]$Name, [string]$Default)
    $path = Join-Path $script:ProjectRoot '.env'
    if (!(Test-Path $path)) { return $Default }
    foreach ($line in [System.IO.File]::ReadAllLines($path)) {
        if ($line.StartsWith("$Name=")) { return $line.Substring($Name.Length + 1).Trim() }
    }
    return $Default
}

function Stop-OptionalIntegrations {
    # Explicit project label prevents stopping another project's containers.
    $ids = @(& docker ps -aq --filter "label=com.docker.compose.project=contribution-ledger" --filter "label=com.contribution-ledger.optional")
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect optional integration services.' }
    $ids = @($ids | Where-Object { $_ -match '^[a-f0-9]+$' })
    if ($ids.Count -gt 0) { & docker stop @ids; if ($LASTEXITCODE -ne 0) { throw 'Could not stop optional integrations.' } }
    # Stop a phase-8 container created before optional labels were introduced.
    $legacy = @(& docker ps -aq --filter "label=com.docker.compose.project=contribution-ledger" --filter "label=com.docker.compose.service=github-worker")
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the earlier import worker.' }
    $legacy = @($legacy | Where-Object { $_ -match '^[a-f0-9]+$' })
    if ($legacy.Count -gt 0) { & docker stop @legacy; if ($LASTEXITCODE -ne 0) { throw 'Could not stop the earlier import worker.' } }
}
