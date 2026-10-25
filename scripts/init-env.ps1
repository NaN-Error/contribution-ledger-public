. (Join-Path $PSScriptRoot 'common.ps1')
$target = Join-Path $script:ProjectRoot '.env'
if (Test-Path $target) { Write-Host 'Existing .env preserved.'; return }
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
$password = -join ($bytes | ForEach-Object { $_.ToString('x2') })
$template = [System.IO.File]::ReadAllText((Join-Path $script:ProjectRoot '.env.example'))
$content = $template.Replace('REPLACE_WITH_GENERATED_PASSWORD', $password)
# CreateNew prevents an unexpected race from overwriting an existing configuration.
$stream = [System.IO.File]::Open($target, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
try {
    $encoded = (New-Object System.Text.UTF8Encoding($false)).GetBytes($content)
    $stream.Write($encoded, 0, $encoded.Length)
} finally { $stream.Dispose() }
Write-Host 'Created .env with a random local database password. Keep this file private.'
