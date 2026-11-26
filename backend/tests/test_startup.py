"""Exercise root startup orchestration without installing or launching services."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell launcher")
def test_root_launcher_forwards_modes_and_restores_working_directory():
    root = Path(__file__).resolve().parents[2]
    script = """
$ErrorActionPreference = 'Stop'
$global:calls = [Collections.Generic.List[string]]::new()
function uv { $global:calls.Add('uv ' + ($args -join ' ')); $global:LASTEXITCODE = 0 }
function npm.cmd { $global:calls.Add('npm ' + ($args -join ' ')); $global:LASTEXITCODE = 0 }
Set-Location -LiteralPath $env:TEMP
$before = (Get-Location).Path
& (Join-Path $env:LEARNEST_TEST_ROOT 'start.ps1') -Desktop -Demo
if ((Get-Location).Path -ne $before) { throw 'Working directory was not restored' }
if ($env:LEARNEST_DEMO -ne '1') { throw 'Demo flag lost' }
$global:calls | ConvertTo-Json -Compress
"""
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script],
        env={**os.environ, "LEARNEST_TEST_ROOT": str(root)}, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == [
        "uv sync --locked --group desktop", "npm ci", "npm run build",
        "uv run --locked --group desktop python -m desktop.launcher",
    ]
