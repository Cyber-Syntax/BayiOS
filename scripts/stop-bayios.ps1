#requires -Version 5.1
# Gracefully stops the BayiOS containers before Windows shuts down or logs off.
# This script never removes volumes, never deletes the database, and never runs
# "compose down -v". If the Podman machine is already down it simply returns.

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$ProjectName = 'bayios',
    [int]$TimeoutSeconds = 30,
    [switch]$StopMachine
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Bayios.Common.psm1') -Force

$root = Get-BayiosRepoRoot -RepoPath $RepoPath
$null = Start-BayiosLog -RepoPath $root -Action 'stop'

try {
    $result = Invoke-BayiosStop -ProjectName $ProjectName -TimeoutSeconds $TimeoutSeconds -StopMachine:$StopMachine

    if (-not $result.MachineRunning) {
        Write-BayiosLog 'Podman machine is not running; nothing to stop.' 'OK'
    } elseif ($result.Stopped.Count -eq 0) {
        Write-BayiosLog 'No running BayiOS containers to stop.' 'OK'
    } else {
        Write-BayiosLog ('Stopped containers: {0}' -f ($result.Stopped -join ', ')) 'OK'
    }

    if ($result.Failed.Count -gt 0) {
        foreach ($failure in $result.Failed) {
            Write-BayiosLog ('Stop failure: {0}' -f $failure) 'ERROR'
        }
        Write-BayiosLog 'Some BayiOS containers could not be stopped cleanly.' 'ERROR'
        exit 1
    }

    Write-BayiosLog 'BayiOS stop completed.' 'OK'
} catch {
    Write-BayiosLog $_.Exception.Message 'ERROR'
    Write-BayiosLog 'Stop failed; no volumes or database were removed.' 'ERROR'
    exit 1
}
