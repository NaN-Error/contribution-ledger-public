. (Join-Path $PSScriptRoot 'common.ps1')
$failed = $false
Write-Host 'Contribution ledger - local environment check'
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host '[FAIL] Docker is missing. Install Docker Desktop with Linux containers, start it, and run this command again.'
    exit 1
}
$containerOS = & docker info --format '{{.OSType}}' 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host '[FAIL] Docker is not running or cannot be accessed.'; $failed = $true }
elseif ($containerOS.Trim() -ne 'linux') { Write-Host '[FAIL] Switch Docker Desktop to Linux containers.'; $failed = $true }
else { Write-Host '[OK] Docker is reachable and uses Linux containers.' }
$composeVersion = & docker compose version --short 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host '[FAIL] Docker Compose v2 is required.'; $failed = $true }
else {
    try { $parsed = [version](($composeVersion -replace '^v','') -split '-')[0] }
    catch { $parsed = [version]'0.0' }
    if ($parsed -lt [version]'2.20.0') { Write-Host '[FAIL] Update Docker Desktop: Compose 2.20 or newer is required.'; $failed = $true }
    else { Write-Host "[OK] Docker Compose $composeVersion" }
}
if (Test-Path (Join-Path $script:ProjectRoot '.env')) { Write-Host '[OK] Local configuration exists; values are not displayed.' }
else { Write-Host '[INFO] Startup will create local configuration without external credentials.' }
Write-Host '[INFO] Windows Python, Node.js, PostgreSQL, GitHub and AI accounts are not required for the Docker workflow.'
Write-Host '[INFO] First build requires internet access to download container images and locked packages.'
if ($failed) { exit 1 }
Write-Host '[OK] Prerequisite checks passed. This is not an application test.'
