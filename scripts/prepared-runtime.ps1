param(
    [ValidateSet('start','stop','token','status','check')][string]$Action = 'start',
    [switch]$NoBrowser,
    [string]$PreparedWorkRoot = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)
)
$ErrorActionPreference = 'Stop'
$taskWork = [IO.Path]::GetFullPath($PreparedWorkRoot)
$appRoot = Join-Path $taskWork 'contribution-ledger'
$practiceRoot = Join-Path $taskWork 'runtime\local-practice'
$pythonExe = Join-Path $taskWork 'verified-env\Scripts\python.exe'
$nodeExe = Join-Path $taskWork 'toolchains\node-v22.16.0-win-x64\node.exe'
$pgBin = Join-Path $taskWork 'toolchains\postgres-runtime\pgsql\bin'
$pgData = Join-Path $practiceRoot 'postgres-data'
$passwordFile = Join-Path $practiceRoot 'postgres-password.txt'
$processFile = Join-Path $practiceRoot 'processes.json'
$webUrl = 'http://127.0.0.1:15173'
$dbPort = 55433
$dbName = 'contribution_ledger_practice'
$dbUser = 'ledger_practice'

function Assert-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing prepared runtime: $Path. Keep the work folder in place." }
}
function Protect-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { New-Item -ItemType Directory -Path $Path | Out-Null }
    if ((Get-Item -LiteralPath $Path).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The private practice directory must not be a link.' }
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    & icacls.exe $Path /inheritance:r /grant:r ('*' + $currentSid.Value + ':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the private practice directory.' }
    $allowedSids = @($currentSid.Value, 'S-1-5-18', 'S-1-5-32-544')
    foreach ($rule in (Get-Acl -LiteralPath $Path).Access) {
        $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($rule.AccessControlType -eq 'Allow' -and $sid -notin $allowedSids) { throw 'The private practice directory has an unexpected access grant.' }
    }
}
function Set-PracticeEnvironment {
    Get-ChildItem Env: | Where-Object { $_.Name.StartsWith('CL_') } | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
    $env:PATH = "$pgBin;$(Split-Path $nodeExe);" + $env:PATH
    $env:PYTHONUTF8 = '1'
    $env:CL_ENVIRONMENT = 'development'
    $env:CL_DB_HOST = '127.0.0.1'
    $env:CL_DB_PORT = [string]$dbPort
    $env:CL_DB_NAME = $dbName
    $env:CL_DB_USER = $dbUser
    $env:CL_DB_PASSWORD = [IO.File]::ReadAllText($passwordFile).Trim()
    $env:CL_ALLOWED_ORIGINS = '["http://127.0.0.1:15173"]'
    $env:CL_AUTH_MASTER_KEY_FILE = Join-Path $practiceRoot 'auth-master\master.key'
    $env:CL_OBJECT_STORAGE_ROOT = Join-Path $practiceRoot 'evidence'
    $env:CL_AI_CREDENTIAL_ROOT = Join-Path $practiceRoot 'ai-credentials'
    $env:CL_AI_MASTER_KEY_FILE = Join-Path $practiceRoot 'ai-master\master.key'
    $env:CL_WEB_INTERNAL_PORT = '15173'
    $env:CL_API_TARGET = 'http://127.0.0.1:18000'
}
function Run-Operator([string]$Command) {
    Push-Location (Join-Path $appRoot 'apps\api')
    try {
        & $pythonExe -m app.cli $Command
        if ($LASTEXITCODE -ne 0) { throw "The $Command operator command failed. Saved data is retained." }
    } finally { Pop-Location }
}
function Owned-Process($Record) {
    if ($null -eq $Record) { return $null }
    $process = Get-Process -Id $Record.pid -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    if ($process.StartTime.ToUniversalTime().Ticks -ne $Record.start_ticks -or $process.Path -ne $Record.path) { return $null }
    return $process
}
function Wait-Http([string]$Url) {
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        try { $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2; if ($response.StatusCode -eq 200) { return } } catch {}
        Start-Sleep -Milliseconds 500
    }
    throw "Service did not become ready: $Url. Inspect the private logs under $practiceRoot."
}
function Record-Process($Process) {
    return @{pid=$Process.Id; start_ticks=$Process.StartTime.ToUniversalTime().Ticks; path=$Process.Path}
}

Assert-File $pythonExe
Assert-File $nodeExe
Assert-File (Join-Path $pgBin 'pg_ctl.exe')
Assert-File (Join-Path $appRoot 'apps\web\dist\index.html')
Protect-Directory $practiceRoot
$state = $null
if (Test-Path -LiteralPath $processFile) { $state = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json }

if ($Action -eq 'stop') {
    foreach ($record in @($state.web, $state.api)) {
        $process = Owned-Process $record
        if ($process) {
            # Kill only the exact process we started and its descendants; a reused PID is refused.
            & taskkill.exe /PID $process.Id /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) {
                # A Windows launcher can exit while taskkill processes its child tree.
                # Accept an already-gone exact process; keep genuine stop failures visible.
                for ($stopAttempt = 0; $stopAttempt -lt 20 -and (Owned-Process $record); $stopAttempt++) {
                    Start-Sleep -Milliseconds 100
                }
                if (Owned-Process $record) { throw 'Could not stop an owned application process.' }
            }
        }
    }
    if (Test-Path -LiteralPath (Join-Path $pgData 'postmaster.pid')) {
        $pgArgs = '-D "' + $pgData + '" -m fast -w stop'
        $control = Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') -ArgumentList $pgArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $practiceRoot 'pg-stop.log') -RedirectStandardError (Join-Path $practiceRoot 'pg-stop-error.log')
        $null = $control.Handle
        $control.WaitForExit()
        if ($control.ExitCode -ne 0) { throw 'The practice database did not stop. Its files are retained.' }
    }
    Write-Host 'Practice app stopped. Accounts, evidence, database and encryption keys are retained.'
    exit 0
}
if ($Action -eq 'status') {
    Wait-Http "$webUrl/web-health"
    Wait-Http "$webUrl/health/ready"
    Write-Host "Practice app is ready: $webUrl"
    exit 0
}
if ($Action -eq 'check') {
    Wait-Http "$webUrl/web-health"
    Wait-Http "$webUrl/health/ready"
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $taskWork 'toolchains\playwright'
    $env:CL_E2E_BASE_URL = $webUrl
    & $pythonExe (Join-Path $appRoot 'tests\e2e\browser_smoke.py')
    if ($LASTEXITCODE -ne 0) { throw 'The browser check failed. Saved practice data is retained.' }
    Write-Host 'PASS: API/database readiness and real-browser account/access/mobile checks.'
    Write-Host 'This check does not create an owner, issue credit, call a provider or make a payment.'
    exit 0
}
if ($Action -eq 'token') {
    Assert-File $passwordFile
    Set-PracticeEnvironment
    Run-Operator 'setup-token'
    Write-Host 'Copy the token above into Setup token in the browser. Choose your own password.'
    exit 0
}

$apiProcess = Owned-Process $state.api
$webProcess = Owned-Process $state.web
if ($apiProcess -and $webProcess) {
    Wait-Http "$webUrl/health/ready"
    Write-Host "Already running: $webUrl"
    if (-not $NoBrowser) { Start-Process $webUrl }
    exit 0
}
foreach ($port in @(18000,15173)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listener -and -not ($apiProcess -and $port -eq 18000) -and -not ($webProcess -and $port -eq 15173)) {
        throw "Port $port is occupied by another process. Nothing was stopped or overwritten."
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $pgData 'PG_VERSION'))) {
    if ((Test-Path -LiteralPath $pgData) -and (Get-ChildItem -LiteralPath $pgData -Force | Select-Object -First 1)) { throw 'An incomplete database directory already exists. Refusing to replace it.' }
    if (-not (Test-Path -LiteralPath $passwordFile)) {
        $bytes = New-Object byte[] 32
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        [IO.File]::WriteAllText($passwordFile, ([BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()))
    }
    $initArgs = '-D "' + $pgData + '" -U ' + $dbUser + ' --pwfile="' + $passwordFile + '" --auth=scram-sha-256 --encoding=UTF8 --locale=C'
    $control = Start-Process -FilePath (Join-Path $pgBin 'initdb.exe') -ArgumentList $initArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $practiceRoot 'pg-init.log') -RedirectStandardError (Join-Path $practiceRoot 'pg-init-error.log')
    $null = $control.Handle
    $control.WaitForExit()
    if ($control.ExitCode -ne 0) { throw 'Practice PostgreSQL initialization failed. Existing files are retained.' }
}
Assert-File $passwordFile
Set-PracticeEnvironment
$pgStatusArgs = '-D "' + $pgData + '" status'
$pgStatusProcess = Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') -ArgumentList $pgStatusArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $practiceRoot 'pg-status.log') -RedirectStandardError (Join-Path $practiceRoot 'pg-status-error.log')
$null = $pgStatusProcess.Handle
$pgStatusProcess.WaitForExit()
$pgStatusCode = $pgStatusProcess.ExitCode
if ($pgStatusCode -notin @(0,3)) { throw 'Could not verify the practice database state. Its files are retained.' }
if ($pgStatusCode -eq 3) {
    if (Get-NetTCPConnection -State Listen -LocalPort $dbPort -ErrorAction SilentlyContinue) { throw "Port $dbPort is already occupied. Refusing to start another database." }
    $pgArgs = '-D "' + $pgData + '" -l "' + (Join-Path $practiceRoot 'postgres.log') + '" -o "-h 127.0.0.1 -p ' + $dbPort + '" -w start'
    $control = Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') -ArgumentList $pgArgs -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $practiceRoot 'pg-start.log') -RedirectStandardError (Join-Path $practiceRoot 'pg-start-error.log')
    $null = $control.Handle
    $control.WaitForExit()
    if ($control.ExitCode -ne 0) { throw 'Practice PostgreSQL did not start. Existing files are retained.' }
}
Push-Location (Join-Path $appRoot 'apps\api')
try {
    & $pythonExe (Join-Path $appRoot 'scripts/prepared_database.py')
    if ($LASTEXITCODE -ne 0) { throw 'Practice database connection failed.' }
} finally { Pop-Location }
Run-Operator 'migrate'
Run-Operator 'init-security'
if (-not $apiProcess) {
    $apiProcess = Start-Process -FilePath $pythonExe -ArgumentList '-m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 18000 --no-access-log --no-proxy-headers' -WorkingDirectory (Join-Path $appRoot 'apps\api') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $practiceRoot 'api.log') -RedirectStandardError (Join-Path $practiceRoot 'api-error.log')
}
$newState = @{api=(Record-Process $apiProcess); web=$state.web; url=$webUrl; private_data=$practiceRoot}
$newState | ConvertTo-Json | Set-Content -LiteralPath $processFile
Wait-Http 'http://127.0.0.1:18000/health/ready'
if (-not $webProcess) {
    $webProcess = Start-Process -FilePath $nodeExe -ArgumentList 'server.mjs' -WorkingDirectory (Join-Path $appRoot 'apps\web') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $practiceRoot 'web.log') -RedirectStandardError (Join-Path $practiceRoot 'web-error.log')
}
$newState.web = Record-Process $webProcess
$newState | ConvertTo-Json | Set-Content -LiteralPath $processFile
Wait-Http "$webUrl/web-health"
Wait-Http "$webUrl/health/ready"
Write-Host "Ready: $webUrl"
Write-Host 'First use: double-click Get-Setup-Token.cmd, then fill in the first-owner form.'
Write-Host 'Later: sign in normally. Stop-Contribution.cmd preserves all saved practice data.'
if (-not $NoBrowser) { Start-Process $webUrl }
