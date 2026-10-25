. (Join-Path $PSScriptRoot 'common.ps1')
Write-Host 'Running container unit/source checks. Native PostgreSQL and browser checks are defined in CI; they require executed results before being considered verified.'
Push-Location $script:ProjectRoot
try {
    & docker build -f infra/api.Dockerfile --target test -t contribution-ledger-api-tests:phase16 .
    if ($LASTEXITCODE -ne 0) { throw 'API test image build failed.' }
    & docker run --rm contribution-ledger-api-tests:phase16
    if ($LASTEXITCODE -ne 0) { throw 'API tests failed.' }
    & docker build -f infra/web.Dockerfile --target test -t contribution-ledger-web-tests:phase16 .
    if ($LASTEXITCODE -ne 0) { throw 'Web test image build failed.' }
    & docker run --rm contribution-ledger-web-tests:phase16
    if ($LASTEXITCODE -ne 0) { throw 'Web tests failed.' }
} finally { Pop-Location }
