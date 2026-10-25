. (Join-Path $PSScriptRoot 'common.ps1')
try {
    # Run the doctor in a child process so its exit code cannot end this script unexpectedly.
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'doctor.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Resolve the prerequisite checks before startup.' }
    & (Join-Path $PSScriptRoot 'init-env.ps1')
    Stop-OptionalIntegrations
    Invoke-Compose stop api
    Invoke-Compose build api web
    Invoke-Compose up -d --wait --wait-timeout 120 db
    Invoke-Compose run --rm --no-deps migrate
    Invoke-Compose up -d --wait --wait-timeout 120 api web
    $webPort = Get-LocalSetting 'CL_WEB_PORT' '5173'
    $apiPort = Get-LocalSetting 'CL_API_PORT' '8000'
    Write-Host "Application: http://127.0.0.1:$webPort"
    Write-Host "API docs: http://127.0.0.1:$apiPort/docs"
    Write-Host 'Startup never creates accounts, seeds or resets data.'
    Write-Host 'For the first installation only, run .\scripts\setup-owner.ps1 and enter its token in the browser.'
} catch {
    Write-Error $_
    exit 1
}
