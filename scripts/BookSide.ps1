param([switch]$Demo, [switch]$Desktop, [switch]$Check)
# Compatibility entry point; startup logic lives in the repository root.
& (Join-Path (Split-Path -Parent $PSScriptRoot) 'BookSide.ps1') @PSBoundParameters
