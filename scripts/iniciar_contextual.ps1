# Inicia explicitamente o ensaio contextual; não escreve no .env nem no banco.
param([switch]$ConfigureOnly)
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
if (-not $ConfigureOnly) {
    & .\.venv-contextual\Scripts\python.exe -m app.run
}
