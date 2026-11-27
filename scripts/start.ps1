#requires -Version 5.1
# Compatibility entry point for the old scripts/start.ps1 shortcut.
# It delegates to the maintained scripts so force-recreate, health checks,
# rollback and the repository-root fix are always used.
#
# Default: build + migrate + force-recreate (same intent as the old script).
# -NoBuild: only start the already-built image.

[CmdletBinding()]
param(
    [switch]$NoBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$target = if ($NoBuild) {
    Join-Path $PSScriptRoot 'start-bayios.ps1'
} else {
    Join-Path $PSScriptRoot 'update-bayios.ps1'
}

if (-not (Test-Path -LiteralPath $target)) {
    throw ('Required script not found: {0}' -f $target)
}

$global:LASTEXITCODE = 0
if ($NoBuild) {
    & $target
} else {
    # Keep the old "build and start" behavior without requiring a clean git
    # tree or taking a backup on every local start. Use update-bayios.ps1
    # directly for a production update with backup.
    & $target -SkipPull -SkipBackup
}

$code = $LASTEXITCODE
if ($code -ne 0) {
    exit $code
}
