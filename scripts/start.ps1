param([switch]$Demo, [switch]$Desktop)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
uv sync
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) { npm.cmd ci }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
if ($Demo) { $env:LEARNEST_DEMO = '1' } else { $env:LEARNEST_DEMO = '0' }
if ($Desktop) {
    uv sync --group desktop
    uv run --group desktop python -m desktop.launcher
} else {
    Write-Host 'LearNest: http://127.0.0.1:8765  (Ctrl+C to stop)'
    uv run uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8765
}

