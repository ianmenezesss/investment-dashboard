param()

function Protect-LogText([string]$Text) {
    $Text = $Text -replace '(?i)postgres(?:ql)?(?:\+[a-z0-9_.-]+)?://[^\s''"\)\]]+', '[DATABASE_URL REDACTED]'
    $Text = $Text -replace '(?im)\b(DATABASE_URL|MIGRATION_DATABASE_URL|TEST_DATABASE_URL|SUPABASE_[A-Z0-9_]+|API_TOKEN|BRAPI_TOKEN)\s*[:=]\s*[^\s,;]+', '$1=[REDACTED]'
    $Text = $Text -replace '(?im)(["'']?(?:password|passwd|token|secret|api[_-]?key)["'']?\s*[:=]\s*["'']?)[^"''\s,;]+', '$1[REDACTED]'
    $Text = $Text -replace '(?i)Authorization:\s*Bearer\s+\S+', 'Authorization: Bearer [REDACTED]'
    return $Text
}

$ErrorActionPreference = 'Stop'
$backend = Split-Path -Parent $PSScriptRoot
$python = Join-Path $backend '.venv\Scripts\python.exe'
$runId = [guid]::NewGuid().ToString('N')
$tempRoot = 'E:\InvestmentDashboard\temp'
$log = Join-Path $tempRoot "investment-dashboard-2.0.8-homologation-$runId.log"
$dockerConfig = Join-Path $tempRoot "docker-config-$runId"
$environmentNames = @('DOCKER_CONFIG','TEMP','TMP','TMPDIR','INVESTMENT_TEMP_DIR','PYTHONDONTWRITEBYTECODE','PYTHONUTF8','PYTHONIOENCODING')
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$exitCode = 1

Write-Host 'Este ensaio grava backups, logs e temporários em E:\InvestmentDashboard\temp.'
Write-Host 'Cria DOIS servidores PostgreSQL descartáveis em bridge Docker exclusiva, sem volumes, usando postgres:17-alpine já em cache.'
Write-Host 'Ele executa migrations e testes fictícios no primeiro servidor, gera pg_dump e restaura no segundo servidor.'
Write-Host 'Não usa .env, banco de desenvolvimento, Supabase, Render ou serviços remotos.'
$confirmation = Read-Host 'Digite exatamente DESCARTAVEL para confirmar que ambos os destinos são descartáveis'
if ($confirmation -cne 'DESCARTAVEL') {
    Write-Host 'Abortado: confirmação explícita não recebida.'
    exit 2
}

try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    if ($env:DOCKER_HOST -or $env:DOCKER_CONTEXT) { throw 'DOCKER_HOST/DOCKER_CONTEXT definido: destino Docker não será presumido local.' }
    $env:TEMP = $tempRoot
    $env:TMP = $tempRoot
    $env:TMPDIR = $tempRoot
    $env:INVESTMENT_TEMP_DIR = $tempRoot
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    New-Item -ItemType Directory -Path $dockerConfig | Out-Null
    $env:DOCKER_CONFIG = $dockerConfig
    $dockerInfo = & docker info --format '{{.ServerVersion}}|{{.DockerRootDir}}' 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Docker Engine indisponível.' }
    $dockerInfoParts = ($dockerInfo | Out-String).Trim() -split '\|', 2
    $dockerVersion = $dockerInfoParts[0]
    $dockerRoot = if ($dockerInfoParts.Count -gt 1) { $dockerInfoParts[1] } else { 'indisponível' }
    $endpoint = (& docker context inspect default --format '{{ .Endpoints.docker.Host }}' 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $endpoint -notmatch '^(npipe:|unix:)') { throw 'O endpoint Docker não é local (npipe/unix); ensaio bloqueado.' }
    $image = & docker image inspect --format '{{.Id}}' postgres:17-alpine 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Imagem postgres:17-alpine ausente no cache; nenhum download será iniciado.' }
    if (-not (Test-Path -LiteralPath $python)) { throw "Python de backend ausente: $python" }

    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($log, "Investment Dashboard 2.0.8 - ensaio local descartável $runId`r`n", $utf8)
    [System.IO.File]::AppendAllText($log, "Docker local: $dockerVersion`r`n", $utf8)
    [System.IO.File]::AppendAllText($log, "DockerRootDir reportado pelo engine (caminho interno, não resolve o disco da VM Desktop): $dockerRoot`r`n", $utf8)
    [System.IO.File]::AppendAllText($log, "Imagem em cache: $(($image | Out-String).Trim())`r`n", $utf8)
    [System.IO.File]::AppendAllText($log, "Endpoint Docker classificado como local: $($endpoint -replace '^(npipe:|unix:).*','$1[local]')`r`n", $utf8)
    Push-Location $backend
    $stdoutPath = Join-Path $tempRoot "runner-stdout-$runId.txt"
    $stderrPath = Join-Path $tempRoot "runner-stderr-$runId.txt"
    try {
        if ((Test-Path -LiteralPath $stdoutPath) -or (Test-Path -LiteralPath $stderrPath)) { throw 'Colisão em arquivo temporário; preservando arquivos existentes.' }
        $runnerPath = Join-Path $PSScriptRoot 'run_postgres.py'
        $process = Start-Process -FilePath $python -ArgumentList @('-u', "`"$runnerPath`"") -WorkingDirectory $backend `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -Wait -PassThru -NoNewWindow
        $exitCode = $process.ExitCode
        $stdoutText = if (Test-Path -LiteralPath $stdoutPath) { [System.IO.File]::ReadAllText($stdoutPath, [System.Text.Encoding]::UTF8) } else { '' }
        $stderrText = if (Test-Path -LiteralPath $stderrPath) { [System.IO.File]::ReadAllText($stderrPath, [System.Text.Encoding]::UTF8) } else { '' }
        $completeOutput = "===== STDOUT =====`r`n$stdoutText`r`n===== STDERR / TRACEBACK COMPLETO =====`r`n$stderrText`r`n===== PROCESS EXIT CODE: $exitCode =====`r`n"
        $safeOutput = Protect-LogText $completeOutput
        [System.IO.File]::AppendAllText($log, $safeOutput, $utf8)
    }
    finally {
        Pop-Location
        foreach ($path in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $path) {
                $resolvedPath = (Resolve-Path -LiteralPath $path).Path
                $resolvedRoot = (Resolve-Path -LiteralPath $tempRoot).Path.TrimEnd('\') + '\'
                if ($resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
                    (Split-Path -Leaf $resolvedPath) -in @("runner-stdout-$runId.txt", "runner-stderr-$runId.txt")) {
                    Remove-Item -LiteralPath $resolvedPath -Force
                }
            }
        }
    }
    if ($exitCode -eq 0) { Write-Host 'Integração e backup/restore descartáveis concluídos.' }
    else { Write-Host "Ensaio falhou (código $exitCode)." }
}
catch {
    $recordText = ($_ | Format-List * -Force | Out-String -Width 8192)
    $message = Protect-LogText ("$($_.Exception.ToString())`r`n$recordText")
    if (Test-Path -LiteralPath $tempRoot) {
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::AppendAllText($log, "ERRO / EXCEÇÃO COMPLETA:`r`n$message`r`n", $utf8)
    }
    Write-Host "Ensaio bloqueado/falhou: $message"
    $exitCode = 1
}
finally {
    foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
    if (Test-Path -LiteralPath $dockerConfig) {
        $resolvedConfig = (Resolve-Path -LiteralPath $dockerConfig).Path
        $resolvedTemp = (Resolve-Path -LiteralPath $tempRoot).Path.TrimEnd('\') + '\'
        if ($resolvedConfig.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase) -and
            (Split-Path -Leaf $resolvedConfig) -eq "investment-dashboard-docker-config-$runId") {
            Remove-Item -LiteralPath $resolvedConfig -Recurse -Force
        }
    }
}

Write-Host "Log consolidado sem URLs de conexão: $log"
exit $exitCode
