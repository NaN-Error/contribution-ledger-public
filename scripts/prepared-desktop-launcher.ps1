param(
    [string]$RuntimeScript = (Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'local-practice.ps1'),
    [string]$AppUrl = 'http://127.0.0.1:15173',
    [switch]$NoBrowser,
    [string]$SmokeTestOutput = '',
    [ValidateSet('start','token')][string]$SmokeTestAction = 'start'
)
# Companion for an already prepared Windows installation. No runtimes are installed here.
$ErrorActionPreference = 'Stop'
if ($SmokeTestOutput -and -not $NoBrowser) { throw 'Rendered smoke checks must disable browser opening.' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$address = [Uri]$AppUrl
if ($address.Scheme -ne 'http' -or $address.Host -ne '127.0.0.1' -or $address.AbsolutePath -ne '/' -or $address.Query -or $address.Fragment) {
    throw 'The prepared launcher requires a local loopback application address.'
}
$RuntimeScript = [IO.Path]::GetFullPath($RuntimeScript)
$lockHash = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($RuntimeScript.ToLowerInvariant()))).Replace('-', '').Substring(0, 16)
$mutex = New-Object Threading.Mutex($false, ('Local\ContributionLedgerWindow' + $lockHash))
try { $ownsMutex = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
if (-not $ownsMutex) {
    try {
        $ready = Invoke-RestMethod ($AppUrl.TrimEnd('/') + '/health/ready') -TimeoutSec 3
        if ($ready.status -eq 'ready') {
            if (-not $NoBrowser) { Start-Process ($AppUrl.TrimEnd('/') + '/#analysis') }
            if ($SmokeTestOutput) {
                [IO.Directory]::CreateDirectory([IO.Path]::GetFullPath($SmokeTestOutput)) | Out-Null
                @{ ready=$true; existing_window_reused=$true; worker_started=$false; browser_opened=$false } |
                    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $SmokeTestOutput 'result.json') -Encoding UTF8
            }
            $mutex.Dispose()
            exit 0
        }
    } catch {}
    [System.Windows.Forms.MessageBox]::Show('Contribution Ledger is already opening. Switch to its startup window.', 'Contribution Ledger') | Out-Null
    $mutex.Dispose()
    exit 0
}
$state = @{ process=$null; output=$null; errors=$null; action=''; busy=$false; ready=$false; copied_code_length=0; operator_exit_code=$null; failure_category=''; deadline=[DateTime]::UtcNow }
$form = New-Object Windows.Forms.Form
$form.Text = 'Contribution Ledger'
$form.ClientSize = New-Object Drawing.Size(560, 350)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.Icon = [Drawing.SystemIcons]::Application
$form.Font = New-Object Drawing.Font('Segoe UI', 10)
$form.BackColor = [Drawing.Color]::FromArgb(247, 247, 252)
$title = New-Object Windows.Forms.Label
$title.Text = 'Your repository dashboard'
$title.Font = New-Object Drawing.Font('Segoe UI', 17, [Drawing.FontStyle]::Bold)
$title.SetBounds(26, 24, 505, 42)
$status = New-Object Windows.Forms.Label
$status.SetBounds(28, 78, 500, 47)
$status.Text = 'Starting Contribution Ledger...'
$progress = New-Object Windows.Forms.ProgressBar
$progress.SetBounds(28, 132, 500, 12)
$progress.Style = 'Marquee'
$hint = New-Object Windows.Forms.Label
$hint.SetBounds(28, 162, 500, 63)
$hint.Text = 'The app will open in your browser. After sign-in, paste a GitHub repository link in the dashboard.'
$open = New-Object Windows.Forms.Button
$open.Text = 'Open dashboard'
$open.SetBounds(28, 234, 163, 38)
$open.BackColor = [Drawing.Color]::FromArgb(106, 75, 176)
$open.ForeColor = [Drawing.Color]::White
$open.FlatStyle = 'Flat'
$open.Enabled = $false
$setup = New-Object Windows.Forms.Button
$setup.Text = 'Copy first-use setup code'
$setup.SetBounds(204, 234, 231, 38)
$setup.Enabled = $false
$retry = New-Object Windows.Forms.Button
$retry.Text = 'Retry'
$retry.SetBounds(445, 234, 83, 38)
$retry.Visible = $false
$footer = New-Object Windows.Forms.Label
$footer.SetBounds(28, 295, 500, 35)
$footer.ForeColor = [Drawing.Color]::FromArgb(90, 90, 105)
$footer.Text = 'Closing this window keeps the app and your saved data available.'
$form.Controls.AddRange(@($title, $status, $progress, $hint, $open, $setup, $retry, $footer))
$timer = New-Object Windows.Forms.Timer
$timer.Interval = 250
function Open-Dashboard {
    if (-not $NoBrowser) { Start-Process ($AppUrl.TrimEnd('/') + '/#analysis') }
}
function Record-Smoke {
    if (-not $SmokeTestOutput) { return }
    $destination = [IO.Path]::GetFullPath($SmokeTestOutput)
    [IO.Directory]::CreateDirectory($destination) | Out-Null
    $image = New-Object Drawing.Bitmap($form.Width, $form.Height)
    try {
        $form.DrawToBitmap($image, (New-Object Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
        $image.Save((Join-Path $destination 'launcher.png'), [Drawing.Imaging.ImageFormat]::Png)
    } finally { $image.Dispose() }
    @{ ready=$state.ready; status=$status.Text; open_enabled=$open.Enabled; setup_enabled=$setup.Enabled; retry_visible=$retry.Visible; runtime_script=$RuntimeScript; browser_opened=$false; copied_code_length=$state.copied_code_length; clipboard_modified=$false; operator_exit_code=$state.operator_exit_code; failure_category=$state.failure_category } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $destination 'result.json') -Encoding UTF8
    $form.Close()
}
function Failed-Start([string]$FailureCategory='operator_failed') {
    $state.failure_category = $FailureCategory
    $state.busy = $false
    $state.ready = $false
    $timer.Stop()
    $progress.Style = 'Blocks'
    $progress.Value = 0
    $status.Text = 'Could not start the app. Your saved data has been kept.'
    $hint.Text = 'Choose Retry. This launcher needs the prepared work folder on this computer; a fresh source download uses Start-local.cmd instead.'
    $retry.Visible = $true
    $open.Enabled = $false
    $setup.Enabled = $false
    Record-Smoke
}
function Start-Operation([string]$Action) {
    if ($state.busy) { return }
    if (-not (Test-Path -LiteralPath $RuntimeScript -PathType Leaf)) { Failed-Start 'missing_runtime'; return }
    $state.busy = $true
    $state.action = $Action
    $state.failure_category = ''
    $state.deadline = [DateTime]::UtcNow.AddMinutes(3)
    $setup.Enabled = $false
    $retry.Visible = $false
    $status.Text = if ($Action -eq 'token') { 'Preparing your first-use setup code...' } else { 'Starting Contribution Ledger...' }
    $progress.Style = 'Marquee'
    $process = New-Object Diagnostics.Process
    $process.StartInfo.FileName = (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')
    $process.StartInfo.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $RuntimeScript + '" -Action ' + $Action + ' -NoBrowser'
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $process.StartInfo.RedirectStandardInput = $true
    # A .NET child launch does not perform PowerShell's PS7 -> Windows PS5
    # module-path cleanup. Use the child's own modules for ACL/network cmdlets.
    $nativeModuleRoot = Join-Path (Split-Path $process.StartInfo.FileName -Parent) 'Modules'
    $process.StartInfo.EnvironmentVariables['PSModulePath'] = $nativeModuleRoot + ';' + (Join-Path $env:ProgramFiles 'WindowsPowerShell\Modules')
    # Setup codes stay in memory. Neither stream is written to a file or displayed in errors.
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    try {
        $null = $process.Start()
        $process.StandardInput.Close()
        $state.process = $process
        $state.output = $process.StandardOutput.ReadToEndAsync()
        $state.errors = $process.StandardError.ReadToEndAsync()
        $timer.Start()
    } catch { $state.busy=$false; $process.Dispose(); Failed-Start }
}
$timer.Add_Tick({
    if (-not $state.process.HasExited) {
        if ([DateTime]::UtcNow -gt $state.deadline) { $status.Text='Starting is taking longer than usual. Please keep this window open.' }
        return
    }
    # A started service can inherit a pipe handle. Startup needs the operator's
    # successful exit plus HTTP readiness, not EOF from its background descendants.
    if (($state.action -eq 'token' -or $state.process.ExitCode -ne 0) -and (-not $state.output.IsCompleted -or -not $state.errors.IsCompleted)) { return }
    $timer.Stop()
    $state.busy = $false
    $exitCode = $state.process.ExitCode
    $state.operator_exit_code = $exitCode
    if ($state.action -eq 'start' -and $exitCode -ne 0 -and $state.output.IsCompleted -and $state.errors.IsCompleted) {
        # Startup diagnostics use the existing restricted runtime directory.
        # Token-command streams are never written to disk.
        $privateDirectory = Join-Path (Split-Path $RuntimeScript -Parent) 'runtime/local-practice'
        if (Test-Path -LiteralPath $privateDirectory -PathType Container) {
            [IO.File]::WriteAllText((Join-Path $privateDirectory 'desktop-start-error.log'), ($state.output.Result + "`n" + $state.errors.Result))
        }
    }
    $output = if ($state.action -eq 'token') { $state.output.Result } else { '' }
    $state.process.Dispose()
    $state.process = $null
    $state.output = $null
    $state.errors = $null
    if ($state.action -eq 'token') {
        $match = [regex]::Match($output, '(?m)^[A-Za-z0-9_-]{43}\r?$')
        if ($exitCode -eq 0 -and $match.Success) {
            if ($SmokeTestOutput) { $state.copied_code_length=$match.Value.Trim().Length }
            else { [Windows.Forms.Clipboard]::SetText($match.Value.Trim()) }
            $status.Text = 'Setup code copied. Paste it into Setup token in the browser.'
            $hint.Text = 'Choose your own name, password, workspace and first project. This setup is needed once; later you can sign in normally.'
            Open-Dashboard
        } else {
            $status.Text = 'A setup code is unavailable. Your account may already be set up.'
            $hint.Text = 'Open the dashboard and sign in. Existing accounts are kept; this button cannot reset a password.'
        }
        $output = $null
        $match = $null
        $setup.Enabled = $true
        $progress.Style = 'Blocks'
        $progress.Value = 100
        Record-Smoke
        return
    }
    $output = $null
    if ($exitCode -ne 0) { Failed-Start; return }
    try {
        $null = Invoke-WebRequest ($AppUrl.TrimEnd('/') + '/web-health') -UseBasicParsing -TimeoutSec 3
        $readiness = Invoke-RestMethod ($AppUrl.TrimEnd('/') + '/health/ready') -TimeoutSec 3
        if ($readiness.status -ne 'ready') { throw 'Not ready' }
    } catch { Failed-Start 'readiness_failed'; return }
    $state.ready = $true
    $status.Text = 'Ready. Open your dashboard and paste a repository link.'
    $hint.Text = 'First time? Copy the setup code below and paste it into Setup token in the browser. After account setup, the repository dashboard opens.'
    $progress.Style = 'Blocks'
    $progress.Value = 100
    $open.Enabled = $true
    $setup.Enabled = $true
    Open-Dashboard
    if ($SmokeTestOutput -and $SmokeTestAction -eq 'token') { $setup.PerformClick(); return }
    Record-Smoke
})
$open.Add_Click({ Open-Dashboard })
$setup.Add_Click({ Start-Operation 'token' })
$retry.Add_Click({ Start-Operation 'start' })
$form.Add_Shown({ Start-Operation 'start' })
$form.Add_FormClosing({ param($sender, $event) if ($state.busy) { $event.Cancel=$true; $status.Text='Please wait while the app finishes starting.' } })
if ($SmokeTestOutput) { $form.Opacity=0; $form.ShowInTaskbar=$false }
try { $null = $form.ShowDialog() } finally {
    $timer.Dispose()
    $form.Dispose()
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
