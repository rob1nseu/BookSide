$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
uv python install 3.11
if ($LASTEXITCODE -ne 0) { throw 'Managed Python installation failed' }
if (-not (Test-Path .venv-build/Scripts/python.exe)) {
    uv venv --python 3.11 --managed-python .venv-build
    if ($LASTEXITCODE -ne 0) { throw 'Build environment creation failed' }
}
$previousUvEnvironment = $env:UV_PROJECT_ENVIRONMENT
try {
    $env:UV_PROJECT_ENVIRONMENT = '.venv-build'
    uv sync --group desktop --group build --no-dev
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
} finally { $env:UV_PROJECT_ENVIRONMENT = $previousUvEnvironment }
Push-Location frontend
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
.\.venv-build\Scripts\pyinstaller.exe --noconfirm --windowed --onedir --name LearNest --paths . --add-data 'backend/app/migrations;backend/app/migrations' --add-data 'backend/app/resources.json;backend/app' --collect-all uvicorn --add-data 'frontend/dist;frontend/dist' --add-data 'desktop/assets;desktop/assets' --hidden-import desktop.companion desktop/launcher.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
# Dependency scanning can resolve Conda DLLs from PATH even in a managed venv.
# Ship the SSL libraries belonging to the exact interpreter used for this build.
$bundlePythonRoot = & .\.venv-build\Scripts\python.exe -c 'import sys; print(sys.base_prefix)'
foreach ($runtimeDll in @('libssl-3-x64.dll', 'libcrypto-3-x64.dll')) {
    Copy-Item -LiteralPath (Join-Path $bundlePythonRoot "DLLs/$runtimeDll") -Destination "dist/LearNest/_internal/$runtimeDll" -Force
}
.\.venv-build\Scripts\python.exe scripts/smoke-windows.py dist/LearNest/LearNest.exe
if ($LASTEXITCODE -ne 0) { throw 'Frozen application validation failed; no ZIP published' }
Compress-Archive -Path dist/LearNest -DestinationPath dist/LearNest-windows-x64.zip -Force

