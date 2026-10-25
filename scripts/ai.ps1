param([ValidateSet('init','start','pause','status','logs','manual')][string]$Action='status',[switch]$WithGitHubSync)
. (Join-Path $PSScriptRoot 'common.ps1')
function Invoke-AICompose {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    Push-Location $script:ProjectRoot
    try {
        $files=@('-f','compose.yaml')
        if ($WithGitHubSync) { $files+=@('-f','compose.github.yaml','-f','compose.sync.yaml') }
        $files+=@('-f','compose.ai.yaml')
        & docker compose --project-directory $script:ProjectRoot @files @Arguments
        if ($LASTEXITCODE -ne 0) { throw 'AI Compose failed. Preserve database, evidence, encrypted credentials and master-key volumes.' }
    } finally { Pop-Location }
}
function Ensure-AIEnvironment {
    $path=Join-Path $script:ProjectRoot '.env'
    if (!(Test-Path -PathType Leaf $path)) { throw 'Run normal local setup first. Read docs/ai_connections.md before enabling a provider.' }
    $lines=@([System.IO.File]::ReadAllLines($path) | Where-Object { $_ -match '^CL_AI_DB_PASSWORD=' })
    if ($lines.Count -gt 1) { throw 'Duplicate AI worker password settings; resolve locally without sharing credentials.' }
    if ($lines.Count -eq 0) {
        $bytes=New-Object byte[] 32
        $rng=[System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $secret=[BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant()
        [System.IO.File]::AppendAllText($path,"`nCL_AI_DB_PASSWORD=$secret`n",(New-Object System.Text.UTF8Encoding($false)))
        $secret=$null
    } elseif ($lines[0] -notmatch '^CL_AI_DB_PASSWORD=[a-f0-9]{64}$') { throw 'Existing AI worker password was not overwritten. Expected a generated 64-character hex value.' }
}
try {
    switch ($Action) {
        'init' {
            Ensure-AIEnvironment
            Stop-OptionalIntegrations
            Invoke-Compose stop api
            Invoke-AICompose build ai-init ai-provision
            Invoke-Compose up -d --wait --wait-timeout 120 db
            Invoke-Compose run --rm --no-deps migrate
            Invoke-AICompose run --rm --no-deps ai-init
            Invoke-AICompose run --rm --no-deps ai-provision
            Write-Host 'Local encrypted storage and restricted worker access prepared. No provider contacted; existing keys preserved.'
            Write-Host 'Run scripts/ai.ps1 -Action start next. Keep .env and both AI volumes private and backed up separately.'
        }
        'start' {
            if ((Get-LocalSetting 'CL_AI_DB_PASSWORD' '') -notmatch '^[a-f0-9]{64}$') { throw 'Run scripts/ai.ps1 -Action init first.' }
            Stop-OptionalIntegrations
            Invoke-Compose stop api
            Invoke-AICompose build api web ai-worker
            Invoke-Compose up -d --wait --wait-timeout 120 db
            Invoke-Compose run --rm --no-deps migrate
            $services=@('api','web','ai-worker')
            if ($WithGitHubSync) {
                Invoke-AICompose build github-celery github-scheduler webhook-gateway
                $services+=@('github-broker','github-celery','github-scheduler','webhook-gateway')
            }
            Invoke-AICompose up -d --wait --wait-timeout 120 @services
            Write-Host 'AI worker started. Defaults permit only the no-cost synthetic provider. Catalog refresh requires the deployment to keep running.'
            Write-Host 'Live providers and paid probes require separate explicit operator settings and payer confirmation.'
        }
        'pause' { Stop-OptionalIntegrations; Write-Host 'Optional integration workers stopped. Already-sent paid requests may still be billed; their reservations remain tracked.' }
        'status' { Invoke-AICompose ps }
        'logs' { Invoke-AICompose logs --tail 100 --follow ai-worker }
        'manual' { Stop-OptionalIntegrations; Invoke-Compose up -d --wait --wait-timeout 120 api web; Write-Host 'Manual-only API restored. All persistent volumes retained.' }
    }
} catch { Write-Error $_; exit 1 }
