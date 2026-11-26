param([switch]$Demo, [switch]$Desktop, [switch]$Check)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
foreach ($tool in @('uv', 'node', 'npm.cmd')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Missing prerequisite: $tool. Install uv and Node.js 22.12+ first."
    }
}
if ($Check) {
    Write-Host "Startup prerequisites available. Project: $projectRoot"
    return
}
Push-Location -LiteralPath $projectRoot
try {
    if ($Desktop) { uv sync --locked --group desktop } else { uv sync --locked }
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
    if ($Demo) { $env:BOOKSIDE_DEMO = '1' } else { $env:BOOKSIDE_DEMO = '0' }
    if ($Desktop) {
        uv run --locked --group desktop python -m desktop.launcher
    } else {
        Write-Host 'BookSide: http://127.0.0.1:8765  (Ctrl+C to stop)'
        uv run --locked uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8765
    }
    if ($LASTEXITCODE -ne 0) { throw 'BookSide exited with an error' }
} finally { Pop-Location }
