param([switch]$Demo, [switch]$Desktop, [switch]$Check)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
if (-not $Check -and -not $Desktop) {
    $existing = $null
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 2
        if ($health.ok) {
            $schema = Invoke-RestMethod 'http://127.0.0.1:8765/openapi.json' -TimeoutSec 2
            if ($schema.info.title -in @('BookSide', 'LearNest')) { $existing = $health }
        }
    } catch { }
    if ($existing) {
        Write-Host 'BookSide is already running: http://127.0.0.1:8765'
        Write-Host 'Reusing the existing service. No dependencies or files were changed.'
        Write-Host 'To load code changes or switch Demo mode, stop the previous launcher first.'
        Write-Host 'If it was started with the desktop pet, use its Exit BookSide menu.'
        return
    }
}
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
    if ($LASTEXITCODE -notin @(0, 130, -1073741510)) {
        throw "BookSide stopped (exit code $LASTEXITCODE). Check the server error above. Port 8765 may already be occupied by another process."
    }
} finally { Pop-Location }
