#requires -Version 5.1
# Stops BayiOS gracefully and then asks Windows to shut down or restart.
# Use this from a desktop shortcut when you want a guaranteed order:
#   BayiOS stop -> Windows shutdown.
# The Group Policy logoff script is the automatic alternative.

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$ProjectName = 'bayios',
    [int]$TimeoutSeconds = 30,
    [int]$DelaySeconds = 10,
    [switch]$Restart,
    [switch]$StopMachine,
    [switch]$ForceShutdown,
    [switch]$NoShutdown
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Bayios.Common.psm1') -Force

$root = Get-BayiosRepoRoot -RepoPath $RepoPath
$null = Start-BayiosLog -RepoPath $root -Action 'shutdown'

try {
    $result = Invoke-BayiosStop -ProjectName $ProjectName -TimeoutSeconds $TimeoutSeconds -StopMachine:$StopMachine

    if ($result.Failed.Count -gt 0) {
        foreach ($failure in $result.Failed) {
            Write-BayiosLog ('Stop failure: {0}' -f $failure) 'ERROR'
        }
        if (-not $ForceShutdown) {
            Write-BayiosLog 'Shutdown aborted because BayiOS did not stop cleanly. Use -ForceShutdown to override.' 'ERROR'
            exit 1
        }
        Write-BayiosLog 'Continuing shutdown despite stop failures because -ForceShutdown was supplied.' 'WARN'
    }

    if ($NoShutdown) {
        Write-BayiosLog 'NoShutdown supplied; Windows shutdown was not requested.' 'WARN'
        return
    }

    if ($env:OS -ne 'Windows_NT') {
        throw 'shutdown-bayios.ps1 is Windows-only (use -NoShutdown for tests).'
    }

    $shutdownExe = Join-Path $env:SystemRoot 'System32\shutdown.exe'
    if (-not (Test-Path -LiteralPath $shutdownExe)) {
        throw ('shutdown.exe not found: {0}' -f $shutdownExe)
    }

    if ($Restart) {
        $shutdownArgs = @('/r', '/t', [string]$DelaySeconds)
        Write-BayiosLog ('Restarting Windows in {0} seconds ...' -f $DelaySeconds) 'WARN'
    } else {
        $shutdownArgs = @('/s', '/t', [string]$DelaySeconds)
        Write-BayiosLog ('Shutting down Windows in {0} seconds ...' -f $DelaySeconds) 'WARN'
    }

    & $shutdownExe @shutdownArgs
    if ($LASTEXITCODE -ne 0) {
        throw ('shutdown.exe failed with exit code {0}' -f $LASTEXITCODE)
    }
} catch {
    Write-BayiosLog $_.Exception.Message 'ERROR'
    exit 1
}
