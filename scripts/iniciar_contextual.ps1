# Inicia explicitamente o ensaio contextual; não escreve no .env nem no banco.
param([switch]$ConfigureOnly, [switch]$Restart, [int]$Port = 5002)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$manifestPath = Join-Path (Get-Location) 'models/contextual/manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw 'Prepare os modelos com python -m scripts.preparar_modelos_contextuais'
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if (-not $manifest.gguf) {
    throw 'Prepare o avaliador GGUF com python -m scripts.preparar_runtime_contextual'
}
$env:CONTEXTUAL_EVALUATOR = 'experimental'
$env:CONTEXTUAL_MODEL_PATH = $manifest.evaluator.path
$env:CONTEXTUAL_MODEL_REVISION = $manifest.evaluator.revision
if ($manifest.gguf) {
    $env:CONTEXTUAL_BACKEND = 'llama_cpp'
    $env:CONTEXTUAL_MODEL_PATH = $manifest.gguf.path
    $env:CONTEXTUAL_MODEL_REVISION = $manifest.gguf.revision
    $env:CONTEXTUAL_RUNTIME_PATH = $manifest.gguf.runtime
    $env:CONTEXTUAL_RUNTIME_REVISION = $manifest.gguf.runtime_sha256
}
$env:EMBEDDING_MODEL = $manifest.retrieval.path
if ($Restart -and -not $ConfigureOnly) {
    $tracePath = Join-Path (Get-Location) 'reports/contextual-server.jsonl'
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    # NetTCP pode não estar disponível; a confirmação HTTP continua sendo obrigatória.
    $response = $null
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/login" -UseBasicParsing -TimeoutSec 5
    } catch {
        if ($listener) { throw 'Porta ocupada sem identidade HTTP confirmada. Nenhum processo foi encerrado.' }
    }
    if ($response) {
        $record = Get-Content -LiteralPath $tracePath | ForEach-Object { $_ | ConvertFrom-Json } |
            Where-Object { $_.event -eq 'FLASK_PROCESS' } | Select-Object -Last 1
        $serverPid = [int]$response.Headers['X-TalentMatch-PID']
        $expectedPython = Join-Path (Get-Location) '.venv-contextual/Scripts/python.exe'
        if (-not $record -or $record.pid -ne $serverPid -or $record.python -ine $expectedPython) {
            throw 'Identidade do servidor não corresponde ao registro local. Nenhum processo foi encerrado.'
        }
        $process = Get-Process -Id $serverPid -ErrorAction Stop
        if ($process.ProcessName -ne 'python') { throw 'Executável inesperado. Reinício cancelado.' }
        # Somente runtimes filhos desse servidor, no diretório autorizado.
        $runtimeRoot = [IO.Path]::GetFullPath((Join-Path (Get-Location) 'models/contextual/llama-cpp/'))
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$serverPid" | Where-Object {
            $_.Name -eq 'llama-server.exe' -and $_.ExecutablePath -and
            ([IO.Path]::GetFullPath($_.ExecutablePath)).StartsWith($runtimeRoot, [StringComparison]::OrdinalIgnoreCase)
        } | ForEach-Object { [Diagnostics.Process]::GetProcessById($_.ProcessId).Kill() }
        $process.Kill()
        if (-not $process.WaitForExit(10000)) { throw 'Servidor anterior não encerrou; reinício cancelado.' }
        Write-Output "Servidor contextual PID $serverPid encerrado; reiniciando na porta $Port."
    }
}
if (-not $ConfigureOnly) {
    & .\.venv-contextual\Scripts\python.exe -m app.run --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Servidor não iniciou. Confira a porta e o diagnóstico acima.' }
}
