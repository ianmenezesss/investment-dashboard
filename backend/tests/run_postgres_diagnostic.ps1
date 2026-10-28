param()

$ErrorActionPreference = 'Continue'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $env:TEMP "investment-dashboard-postgres-$stamp.log"
$pythonLog = Join-Path $env:TEMP "investment-dashboard-postgres-tests-$stamp.log"
$dockerConfig = Join-Path $env:TEMP "investment-dashboard-docker-config-$stamp"
$backend = Split-Path -Parent $PSScriptRoot
$python = Join-Path $backend '.venv\Scripts\python.exe'
$exitCode = 1
$previousDockerConfig = $env:DOCKER_CONFIG

New-Item -ItemType Directory -Path $dockerConfig -Force | Out-Null
$env:DOCKER_CONFIG = $dockerConfig

Start-Transcript -Path $log -Force | Out-Null
try {
    Write-Host "Workspace: $backend"
    Write-Host "Log completo: $log"
    Write-Host 'Integração 001–007; hashes dos arquivos em execução:'
    Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $backend 'migrations/versions/006_application_revisions.py'), (Join-Path $backend 'migrations/versions/007_revision_runtime_api.py'), (Join-Path $PSScriptRoot 'test_postgres.py'), (Join-Path $PSScriptRoot 'application_revisions_postgres.py') | Format-List Path, Hash
    Write-Host 'Verificando Docker Engine e imagem local postgres:17-alpine (sem pull)...'

    docker info --format '{{.ServerVersion}}'
    if ($LASTEXITCODE -ne 0) { throw "Docker Engine indisponível (exit $LASTEXITCODE). Consulte o log." }
    docker image inspect --format '{{.Id}}' postgres:17-alpine
    if ($LASTEXITCODE -ne 0) { throw "Imagem postgres:17-alpine não está em cache; o script não fará download." }
    if (-not (Test-Path -LiteralPath $python)) { throw "Python da venv não encontrado: $python" }

    Push-Location $backend
    try {
        # Native child output is redirected explicitly; Windows PowerShell 5 transcripts
        # do not reliably retain pytest's subprocess traceback on their own.
        & $python -u (Join-Path $PSScriptRoot 'run_postgres.py') *> $pythonLog
        $exitCode = $LASTEXITCODE
    }
    finally { Pop-Location }
}
catch {
    Write-Host "ERRO: $($_.Exception.Message)"
    $exitCode = 1
}
finally {
    Stop-Transcript | Out-Null
    $env:DOCKER_CONFIG = $previousDockerConfig
}

if (Test-Path -LiteralPath $pythonLog) {
    Add-Content -LiteralPath $log -Value "`r`n===== Saída completa do runner/pytest ====="
    Add-Content -LiteralPath $log -Value (Get-Content -LiteralPath $pythonLog -Raw)
}
Write-Host "Log completo salvo em: $log"
exit $exitCode
