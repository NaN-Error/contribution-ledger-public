param([ValidateSet('start','pause','status','logs','step','manual','provision')][string]$Action='status')
. (Join-Path $PSScriptRoot 'common.ps1')
function Invoke-GitHubCompose {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
    Push-Location $script:ProjectRoot
    try {
        & docker compose --project-directory $script:ProjectRoot -f (Join-Path $script:ProjectRoot 'compose.yaml') -f (Join-Path $script:ProjectRoot 'compose.github.yaml') @Arguments
        if ($LASTEXITCODE -ne 0) { throw "GitHub Compose operation failed (exit $LASTEXITCODE). Preserve configuration, secrets and database volumes." }
    } finally { Pop-Location }
}
try {
    if (!(Test-Path (Join-Path $script:ProjectRoot '.env'))) { throw 'Run the normal startup once before configuring the optional GitHub profile.' }
    if ($Action -eq 'provision') {
        foreach ($name in @('github-private-key.pem','github-client-secret')) {
            if (!(Test-Path -PathType Leaf (Join-Path $script:ProjectRoot ".local/github-secrets/$name"))) { throw "Missing protected mount file: $name. Follow docs/github_setup.md; do not paste its contents into chat." }
        }
        if ((Get-LocalSetting 'CL_GITHUB_APP_ID' '') -notmatch '^[1-9][0-9]*$') { throw 'Set CL_GITHUB_APP_ID in .env to the numeric App ID (not the installation ID).' }
        if ((Get-LocalSetting 'CL_GITHUB_CLIENT_ID' '') -notmatch '^[A-Za-z0-9_.-]{3,100}$') { throw 'Set the non-secret CL_GITHUB_CLIENT_ID in .env.' }
    }
    switch ($Action) {
        'provision' {
            Write-Host 'This copies the required credential files and an optional webhook secret into a private Docker volume. It stops the API and worker first. Existing credentials will be replaced, and pending authorization attempts must restart.'
            $confirmation=Read-Host 'Type PROVISION GITHUB SECRETS to continue'
            if ($confirmation -ne 'PROVISION GITHUB SECRETS') { Write-Host 'Cancelled.'; exit 0 }
            Stop-OptionalIntegrations
            Invoke-GitHubCompose stop api github-worker
            Invoke-Compose build api
            Invoke-GitHubCompose run --rm --no-deps github-provision python -m app.security.secrets.provision --confirm 'PROVISION GITHUB SECRETS'
            Write-Host 'Provisioned. Run this script with -Action start to resume. Protect the host staging files and secret volume backups.'
        }
        'start' {
            Stop-OptionalIntegrations
            Invoke-GitHubCompose stop github-worker
            Invoke-Compose stop api
            Invoke-GitHubCompose build api web github-worker
            Invoke-GitHubCompose up -d --wait --wait-timeout 120 db
            Invoke-Compose run --rm --no-deps migrate
            Invoke-GitHubCompose up -d --wait --wait-timeout 120 api web github-worker
            $port=Get-LocalSetting 'CL_WEB_PORT' '5173'
            Write-Host "Open http://127.0.0.1:$port and the project GitHub tab. No import or authorization is created by startup."
        }
        'pause' { Stop-OptionalIntegrations
            Invoke-GitHubCompose stop github-worker; Write-Host 'Worker paused. Queued imports remain in the database.' }
        'status' { Invoke-GitHubCompose ps }
        'logs' { Invoke-GitHubCompose logs --tail 100 --follow github-worker }
        'step' { Invoke-GitHubCompose run --rm --no-deps github-worker python -m app.workers.github --max-steps 1 }
        'manual' {
            Stop-OptionalIntegrations
            Invoke-GitHubCompose stop github-worker
            Invoke-Compose up -d --wait --wait-timeout 120 api web
            Write-Host 'GitHub disabled on the API; separate worker stopped. Captured history and queued imports are retained. This does not uninstall the GitHub App.'
        }
    }
} catch { Write-Error $_; exit 1 }
