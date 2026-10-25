param([ValidateSet('init','start','pause','status','logs','manual')][string]$Action='status')
. (Join-Path $PSScriptRoot 'common.ps1')
function Invoke-SyncCompose {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    Push-Location $script:ProjectRoot
    try {
        & docker compose --project-directory $script:ProjectRoot -f compose.yaml -f compose.github.yaml -f compose.sync.yaml @Arguments
        if ($LASTEXITCODE -ne 0) { throw 'Synchronization Compose failed. Preserve database, evidence and secret volumes.' }
    } finally { Pop-Location }
}
function New-PrivateHex {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant()
}
try {
    $envPath=Join-Path $script:ProjectRoot '.env'
    if (!(Test-Path -PathType Leaf $envPath)) { throw 'Run normal setup first. Then read docs/github_sync.md.' }
    switch ($Action) {
        'init' {
            $lines=@([System.IO.File]::ReadAllLines($envPath) | Where-Object { $_ -match '^CL_JOBS_BROKER_PASSWORD=' })
            if ($lines.Count -gt 1) { throw 'Duplicate broker settings; resolve them locally without sharing secrets.' }
            if ($lines.Count -eq 0) {
                $secret=New-PrivateHex
                [System.IO.File]::AppendAllText($envPath,"`nCL_JOBS_BROKER_PASSWORD=$secret`n",(New-Object System.Text.UTF8Encoding($false)))
                $secret=$null
            } elseif ($lines[0] -notmatch '^CL_JOBS_BROKER_PASSWORD=[a-f0-9]{64}$') { throw 'The existing broker setting is not a generated 64-character hex value. It was not overwritten.' }
            $folder=Join-Path $script:ProjectRoot '.local/github-secrets'
            [System.IO.Directory]::CreateDirectory($folder) | Out-Null
            $file=Join-Path $folder 'github-webhook-secret'
            if (!(Test-Path $file)) {
                $bytes=[System.Text.Encoding]::ASCII.GetBytes((New-PrivateHex))
                $stream=[System.IO.File]::Open($file,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
                try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
            }
            Write-Host 'Generated missing local secrets; existing values were preserved. Nothing was sent to GitHub.'
            Write-Host 'Protect .env and .local with your Windows account permissions. Do not commit them or send them in chat.'
            Write-Host 'Before enabling webhooks, privately put the webhook secret into your App settings and re-run github.ps1 -Action provision.'
        }
        'start' {
            if ((Get-LocalSetting 'CL_JOBS_BROKER_PASSWORD' '') -notmatch '^[a-f0-9]{64}$') { throw 'Run scripts/sync.ps1 -Action init before enabling synchronization.' }
            Stop-OptionalIntegrations
            Invoke-Compose stop api
            Invoke-SyncCompose build api web github-celery github-scheduler webhook-gateway
            Invoke-Compose up -d --wait --wait-timeout 120 db
            Invoke-Compose run --rm --no-deps migrate
            Invoke-SyncCompose up -d --wait --wait-timeout 120 api web github-broker github-celery github-scheduler webhook-gateway
            Write-Host 'Optional local synchronization services started. Enable a repository schedule explicitly in GitHub > Synchronization.'
            Write-Host 'The webhook gateway is localhost-only. No public endpoint, GitHub subscription or repository permission was created.'
        }
        'pause' { Stop-OptionalIntegrations; Write-Host 'Optional workers, scheduler, broker and gateway stopped. Database records and approved schedules were retained.' }
        'status' { Invoke-SyncCompose ps }
        'logs' { Invoke-SyncCompose logs --tail 100 --follow github-scheduler github-celery }
        'manual' { Stop-OptionalIntegrations; Invoke-Compose up -d --wait --wait-timeout 120 api web; Write-Host 'Manual-only operation restored. No database or evidence volume was deleted.' }
    }
} catch { Write-Error $_; exit 1 }
