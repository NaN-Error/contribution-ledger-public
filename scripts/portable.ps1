param(
    [ValidateSet('start','stop','status')][string]$Action = 'start',
    [string]$DataDirectory = (Join-Path $env:LOCALAPPDATA 'ContributionLedger\Personal'),
    [switch]$NoBrowser
)
# Auditable orchestration. No analyzed code execution or silent dependency installation.
$ErrorActionPreference = 'Stop'
# A child launched from PS7/Python can inherit incompatible PS7 module paths.
# This native PS5 operator uses only its own system modules for ACL/network checks.
if ($PSVersionTable.PSEdition -eq 'Desktop') {
    $env:PSModulePath=(Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\Modules')+';'+(Join-Path $env:ProgramFiles 'WindowsPowerShell\Modules')
}
$appRoot = Split-Path $PSScriptRoot -Parent
$privateRoot = [IO.Path]::GetFullPath($DataDirectory)
$pythonExe = Join-Path $appRoot 'runtime\python\python.exe'
$nodeExe = Join-Path $appRoot 'runtime\node\node.exe'
$pgBin = Join-Path $appRoot 'runtime\postgres\pgsql\bin'
$pgData = Join-Path $privateRoot 'postgres-data'
$processFile = Join-Path $privateRoot 'processes.json'
$passwordFile = Join-Path $privateRoot 'postgres-password.txt'
$settingsFile = Join-Path $privateRoot 'ports.json'
$dbName = 'contribution_ledger_desktop'
$dbUser = 'ledger_desktop'
$state = $null

function Protect-Data {
    $marker=Join-Path $privateRoot 'personal-installation.json'
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    if ($privateRoot.TrimEnd('\') -eq [IO.Path]::GetPathRoot($privateRoot).TrimEnd('\')) { throw 'A drive root cannot be the personal data directory.' }
    $programRoot=[IO.Path]::GetFullPath($appRoot).TrimEnd('\')
    if ($privateRoot.Equals($programRoot,[StringComparison]::OrdinalIgnoreCase) -or
        $privateRoot.StartsWith($programRoot+'\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Keep personal data outside the program folder so source and release packages cannot include it.'
    }
    if (Test-Path -LiteralPath $privateRoot) {
        if (-not (Test-Path -LiteralPath $privateRoot -PathType Container)) { throw 'The data path must be a directory.' }
        if (Test-Path -LiteralPath $marker -PathType Leaf) {
            if ((Get-Item -LiteralPath $marker).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The installation marker must not be redirected.' }
            $existing=Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
            if ($existing.format -ne 1 -or $existing.application -ne 'ContributionLedgerPersonal' -or $existing.windows_user_sid -ne $sid) { throw 'This directory does not belong to this Windows personal installation.' }
        } elseif (Get-ChildItem -LiteralPath $privateRoot -Force | Select-Object -First 1) {
            throw 'The selected data directory already contains unrelated files. Nothing was adopted or changed.'
        }
    }
    $ancestor = $privateRoot
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor) {
            if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The data path must not contain directory links.' }
        }
        $parent = Split-Path $ancestor -Parent
        if ($parent -eq $ancestor) { break }; $ancestor = $parent
    }
    if (-not (Test-Path -LiteralPath $privateRoot)) { New-Item -ItemType Directory -Path $privateRoot | Out-Null }
    & icacls.exe $privateRoot /inheritance:r /grant:r ('*' + $sid + ':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not protect your local data directory.' }
    foreach ($rule in (Get-Acl -LiteralPath $privateRoot).Access) {
        if ($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @($sid,'S-1-5-18','S-1-5-32-544')) { throw 'The data directory has an unexpected access grant.' }
    }
    foreach ($item in (Get-ChildItem -LiteralPath $privateRoot -Force)) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Private data must not contain redirected files or directories.' }
    }
    if (-not (Test-Path -LiteralPath $marker)) {
        @{format=1;application='ContributionLedgerPersonal';windows_user_sid=$sid} | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
    }
}
function Owned-Process($Record, [string]$Executable) {
    if ($null -eq $Record) { return $null }
    $expected = [IO.Path]::GetFullPath($Executable)
    $proc = Get-Process -Id $Record.pid -ErrorAction SilentlyContinue
    # Recover an older blank path only with the exact PID, creation time and
    # known executable for this service. Never adopt a foreign port/process.
    if ($null -eq $proc -or $proc.StartTime.ToUniversalTime().Ticks -ne $Record.start_ticks -or
        $proc.Path -ne $expected -or ($Record.path -and $Record.path -ne $expected)) { return $null }
    return $proc
}
function Process-Record($Proc, [string]$Executable) {
    # Start-Process can return before its cached MainModule/Path is available.
    # Record the exact FilePath supplied by this launcher instead of that cache.
    $expected = [IO.Path]::GetFullPath($Executable)
    if ($Proc.Path -and $Proc.Path -ne $expected) { throw 'Unexpected launched executable; nothing was adopted.' }
    return @{pid=$Proc.Id; start_ticks=$Proc.StartTime.ToUniversalTime().Ticks; path=$expected}
}
function Save-State { $state | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding UTF8 }
function Wait-Ready([string]$Url) {
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        try { $value = Invoke-RestMethod -Uri $Url -TimeoutSec 2; if ($value.status -eq 'ready') { return $value } } catch {}
        Start-Sleep -Milliseconds 500
    }
    throw 'The local app did not become ready. Inspect the private logs; keep your saved data.'
}
function Operator([string]$Command) {
    Push-Location (Join-Path $appRoot 'apps\api')
    try {
        & $pythonExe -m app.cli $Command
        if ($LASTEXITCODE -ne 0) { throw ('Local operation failed: ' + $Command + '. Saved data was kept.') }
    } finally { Pop-Location }
}
function Pg-Control([string]$Arguments, [string]$LogName) {
    $proc = Start-Process -FilePath (Join-Path $pgBin 'pg_ctl.exe') -ArgumentList $Arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $privateRoot ($LogName+'.log')) -RedirectStandardError (Join-Path $privateRoot ($LogName+'-error.log'))
    $null=$proc.Handle; $proc.WaitForExit(); return $proc.ExitCode
}
function Pick-Port {
    for ($attempt=0; $attempt -lt 100; $attempt++) {
        $port = Get-Random -Minimum 32000 -Maximum 50000
        $socket = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $port)
        try { $socket.Start(); return $port } catch {} finally { $socket.Stop() }
    }
    throw 'Could not find a free local port.'
}
function Windows-Runtime-Ready {
    foreach ($name in @('msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll')) {
        $path=Join-Path $env:SystemRoot ('System32\'+$name)
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $false }
        if ((Get-Item -LiteralPath $path).VersionInfo.FileVersionRaw -lt [Version]'14.44.35211.0') { return $false }
    }
    return $true
}
function Ensure-Windows-Runtime {
    if (Windows-Runtime-Ready) { return }
    if ($NoBrowser) { throw 'Microsoft Visual C++ x64 runtime is needed. Normal Start.cmd opens Microsoft setup; unattended checks never install it.' }
    Write-Host 'Microsoft Visual C++ runtime is needed once. Its setup will ask for your approval.'
    Write-Host 'The installer is downloaded from Microsoft, checksum-checked and signature-verified.'
    $lock=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'windows-runtime-lock.json') -Raw | ConvertFrom-Json
    $prerequisite=$lock.optional_windows_prerequisite
    if ($prerequisite.url -ne 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -or $prerequisite.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Invalid Microsoft runtime download configuration.' }
    $folder=Join-Path $privateRoot 'windows-prerequisites'
    if (-not (Test-Path -LiteralPath $folder)) { New-Item -ItemType Directory -Path $folder | Out-Null }
    if ((Get-Item -LiteralPath $folder).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The runtime-download directory must not be redirected.' }
    $installer=Join-Path $folder 'vc_redist.x64.exe'
    if (Test-Path -LiteralPath $installer) {
        if ((Get-Item -LiteralPath $installer).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'The cached Microsoft installer must not be redirected.' }
    } else {
        [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $prerequisite.url -OutFile $installer -UseBasicParsing -TimeoutSec 120
    }
    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $prerequisite.sha256) {
        throw 'Microsoft installer checksum changed. Nothing was executed; obtain an updated reviewed package.'
    }
    $signature=Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|, )O=Microsoft Corporation(,|$)') { throw 'Microsoft installer signature could not be verified. Nothing was executed.' }
    # Interactive official setup retains its license/UAC choices. Never accept them silently.
    $proc=Start-Process -FilePath $installer -ArgumentList '/norestart' -WindowStyle Normal -PassThru
    $null=$proc.Handle; $proc.WaitForExit()
    if ($proc.ExitCode -notin @(0,3010) -or -not (Windows-Runtime-Ready)) { throw 'Microsoft runtime setup did not finish. You can reopen Start.cmd; saved data is kept.' }
    if ($proc.ExitCode -eq 3010) { Write-Host 'Microsoft setup recommends a Windows restart. This launcher never restarts Windows.' }
}
function Open-Personal {
    # The operator ticket is captured only in memory; never printed or logged.
    $lines = @(Operator 'desktop-ticket')
    $record = ($lines | Where-Object { $_ -match '^\{"desktop_ticket":' } | Select-Object -Last 1) | ConvertFrom-Json
    if ($null -eq $record -or $record.desktop_ticket -notmatch '^[A-Za-z0-9_-]{43}$') { throw 'Personal setup could not finish. No accounts were reset.' }
    if (-not $NoBrowser) { Start-Process ($webUrl + '/#desktop/' + $record.desktop_ticket) }
    $record=$null; $lines=$null
    Write-Host 'Ready. Paste a public GitHub repository link in the dashboard.'
}

$hash = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($privateRoot.ToLowerInvariant()))).Replace('-','').Substring(0,16)
$mutex = New-Object Threading.Mutex($false, ('Local\ContributionLedgerPortable'+$hash))
$owns=$false
try {
    try { $owns=$mutex.WaitOne(120000) } catch [Threading.AbandonedMutexException] { $owns=$true }
    if (-not $owns) { throw 'Another startup is still preparing this installation. Wait and open Start.cmd again.' }
    foreach ($file in @($pythonExe,$nodeExe,(Join-Path $pgBin 'pg_ctl.exe'),(Join-Path $appRoot 'apps\web\dist\index.html'))) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'This is not the complete Windows package. Download and extract the package including runtime\.' }
    }
    Protect-Data
    if ($Action -eq 'start') { Ensure-Windows-Runtime }
    if (Test-Path -LiteralPath $processFile) { $state=Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json }
    if ($Action -eq 'stop') {
        foreach ($service in @(@{record=$state.web;executable=$nodeExe},@{record=$state.api;executable=$pythonExe})) {
            $record=$service.record
            $proc=Owned-Process $record $service.executable
            if ($proc) {
                & taskkill.exe /PID $proc.Id /T /F | Out-Null
                if ($LASTEXITCODE -ne 0 -and (Owned-Process $record $service.executable)) { throw 'Could not stop an owned process. Nothing was deleted.' }
            }
        }
        if (Test-Path -LiteralPath (Join-Path $pgData 'postmaster.pid')) {
            $code=Pg-Control ('-D "'+$pgData+'" status') 'pg-status'
            if ($code -eq 0 -and (Pg-Control ('-D "'+$pgData+'" -m fast -w -t 300 stop') 'pg-stop') -ne 0) { throw 'Could not stop the local database. Its data was retained.' }
            if ($code -notin @(0,3)) { throw 'Could not check the local database state.' }
        }
        Write-Host 'Stopped. Your projects, evidence and encryption keys are kept.'; exit 0
    }
    if (-not (Test-Path -LiteralPath $settingsFile)) {
        if ($Action -ne 'start') { throw 'This personal installation has not started yet.' }
        $ports=@{db=(Pick-Port);api=(Pick-Port);web=(Pick-Port)}
        if (@($ports.db,$ports.api,$ports.web | Select-Object -Unique).Count -ne 3) { throw 'Local ports overlapped. Open Start.cmd again.' }
        $ports | ConvertTo-Json | Set-Content -LiteralPath $settingsFile -Encoding UTF8
    }
    $ports=Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
    foreach ($port in @($ports.db,$ports.api,$ports.web)) { if ($port -isnot [int] -or $port -lt 1024 -or $port -gt 65535) { throw 'Invalid saved local port configuration. No data was changed.' } }
    if (@($ports.db,$ports.api,$ports.web | Select-Object -Unique).Count -ne 3) { throw 'Saved local ports overlap.' }
    $webUrl='http://127.0.0.1:'+$ports.web
    if ($Action -eq 'status') { $null=Wait-Ready ($webUrl+'/health/ready'); Write-Host ('Ready: '+$webUrl); exit 0 }
    Write-Host 'Starting your personal Contribution Ledger dashboard...'
    Get-ChildItem Env: | Where-Object { $_.Name.StartsWith('CL_') } | ForEach-Object { Remove-Item -LiteralPath ('Env:'+$_.Name) }
    $env:PYTHONHOME=$null; $env:PYTHONPATH=$null; $env:PYTHONUTF8='1'; $env:PYTHONDONTWRITEBYTECODE='1'
    $env:CL_ENVIRONMENT='development'; $env:CL_DESKTOP_ENABLED='true'
    $env:CL_ALLOWED_HOSTS='["127.0.0.1","localhost"]'; $env:CL_ALLOWED_ORIGINS='["'+$webUrl+'"]'
    $env:CL_DB_HOST='127.0.0.1'; $env:CL_DB_PORT=[string]$ports.db; $env:CL_DB_NAME=$dbName; $env:CL_DB_USER=$dbUser
    $env:CL_AUTH_MASTER_KEY_FILE=Join-Path $privateRoot 'auth-master\master.key'
    $env:CL_OBJECT_STORAGE_ROOT=Join-Path $privateRoot 'evidence'
    $env:CL_AI_CREDENTIAL_ROOT=Join-Path $privateRoot 'ai-credentials'; $env:CL_AI_MASTER_KEY_FILE=Join-Path $privateRoot 'ai-master\master.key'
    $env:CL_REPOSITORY_PRIVATE_READS_ENABLED='true'
    $env:CL_REPOSITORY_CREDENTIAL_ROOT=Join-Path $privateRoot 'github-credentials'
    $env:CL_REPOSITORY_MASTER_KEY_FILE=Join-Path $privateRoot 'github-master\master.key'
    $env:CL_WEB_INTERNAL_PORT=[string]$ports.web; $env:CL_API_TARGET='http://127.0.0.1:'+$ports.api
    $apiProcess=Owned-Process $state.api $pythonExe; $webProcess=Owned-Process $state.web $nodeExe
    if (-not (Test-Path -LiteralPath (Join-Path $pgData 'PG_VERSION'))) {
        if ((Test-Path -LiteralPath $pgData) -and (Get-ChildItem -LiteralPath $pgData -Force | Select-Object -First 1)) { throw 'An incomplete database directory exists. Refusing to replace it.' }
        if (-not (Test-Path -LiteralPath $passwordFile)) {
            $bytes=New-Object byte[] 32; $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
            try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
            [IO.File]::WriteAllText($passwordFile,[BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant())
        }
        Write-Host 'Preparing the local database for first use. This can take several minutes on a busy disk.'
        $arguments='-D "'+$pgData+'" -U '+$dbUser+' --pwfile="'+$passwordFile+'" --auth=scram-sha-256 --encoding=UTF8 --locale=C'
        $proc=Start-Process -FilePath (Join-Path $pgBin 'initdb.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $privateRoot 'pg-init.log') -RedirectStandardError (Join-Path $privateRoot 'pg-init-error.log')
        $null=$proc.Handle; $proc.WaitForExit(); if ($proc.ExitCode -ne 0) { throw 'Database initialization failed. Its files were kept.' }
    }
    if (-not (Test-Path -LiteralPath $passwordFile)) { throw 'The retained database password is missing. Refusing to replace it.' }
    $env:CL_DB_PASSWORD=[IO.File]::ReadAllText($passwordFile).Trim()
    $pgStatus=Pg-Control ('-D "'+$pgData+'" status') 'pg-status'
    if ($pgStatus -notin @(0,3)) { throw 'Could not verify the retained database state.' }
    if ($pgStatus -eq 3) {
        if (Get-NetTCPConnection -State Listen -LocalPort $ports.db -ErrorAction SilentlyContinue) { throw 'The saved database port is occupied. Nothing was stopped.' }
        if ((Pg-Control ('-D "'+$pgData+'" -l "'+(Join-Path $privateRoot 'postgres.log')+'" -o "-h 127.0.0.1 -p '+$ports.db+'" -w -t 300 start') 'pg-start') -ne 0) { throw 'Local PostgreSQL could not start. Its data was kept.' }
    }
    if ($apiProcess -and $webProcess) {
        $ready=Wait-Ready ($webUrl+'/health/ready')
        if ($ready.version -ne [IO.File]::ReadAllText((Join-Path $appRoot 'VERSION')).Trim()) { throw 'Another version is running. Stop it using its Stop.cmd before opening this package.' }
        Open-Personal; exit 0
    }
    foreach ($item in @(@{port=$ports.api;proc=$apiProcess},@{port=$ports.web;proc=$webProcess})) {
        if (-not $item.proc -and (Get-NetTCPConnection -State Listen -LocalPort $item.port -ErrorAction SilentlyContinue)) { throw 'A saved app port is occupied by another process. Nothing was stopped.' }
    }
    Push-Location (Join-Path $appRoot 'apps\api')
    try { & $pythonExe (Join-Path $PSScriptRoot 'portable_database.py'); if ($LASTEXITCODE -ne 0) { throw 'Could not open the personal database.' } } finally { Pop-Location }
    Operator 'migrate'; Operator 'init-security'
    Operator 'init-repository-credentials'
    if (-not $apiProcess) {
        $apiProcess=Start-Process -FilePath $pythonExe -ArgumentList ('-m uvicorn app.main:create_app --factory --host 127.0.0.1 --port '+$ports.api+' --no-access-log --no-proxy-headers') -WorkingDirectory (Join-Path $appRoot 'apps\api') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $privateRoot 'api.log') -RedirectStandardError (Join-Path $privateRoot 'api-error.log')
    }
    $state=@{api=(Process-Record $apiProcess $pythonExe);web=$state.web;url=$webUrl;private_data=$privateRoot}; Save-State
    $null=Wait-Ready ('http://127.0.0.1:'+$ports.api+'/health/ready')
    if (-not $webProcess) {
        $webProcess=Start-Process -FilePath $nodeExe -ArgumentList 'server.mjs' -WorkingDirectory (Join-Path $appRoot 'apps\web') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $privateRoot 'web.log') -RedirectStandardError (Join-Path $privateRoot 'web-error.log')
    }
    $state.web=Process-Record $webProcess $nodeExe; Save-State
    $null=Wait-Ready ($webUrl+'/health/ready')
    Open-Personal
} catch {
    # No raw operator ticket or database password belongs in diagnostics.
    Write-Host ('Could not start: '+$_.Exception.Message)
    Write-Host ('Your data is kept at '+$privateRoot)
    exit 1
} finally {
    if ($owns) { $mutex.ReleaseMutex() }; $mutex.Dispose()
}
