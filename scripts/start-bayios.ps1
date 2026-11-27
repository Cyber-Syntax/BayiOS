#requires -Version 5.1
# Starts the already-built BayiOS stack. Intended for Windows Task Scheduler
# at logon. It never builds, never deletes volumes, and never runs migrations.

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$ProjectName = 'bayios',
    [string]$ComposeFile = '',
    [int]$Port = 0,
    [int]$TimeoutSeconds = 240,
    [switch]$NoMachine
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Bayios.Common.psm1') -Force

$root = Get-BayiosRepoRoot -RepoPath $RepoPath
if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
    $ComposeFile = Join-Path $root 'compose.yaml'
}
$port = Get-BayiosPort -RepoPath $root -Port $Port

$null = Start-BayiosLog -RepoPath $root -Action 'start'
$lock = $null

try {
    $lock = New-BayiosLock -RepoPath $root

    if (-not $NoMachine) {
        Start-BayiosPodmanMachine -TimeoutSeconds $TimeoutSeconds
    }

    Assert-BayiosPrerequisites -RepoPath $root -ComposeFile $ComposeFile

    $imageId = Get-BayiosImageId -Image 'localhost/bayios:latest'
    if (-not $imageId) {
        throw 'localhost/bayios:latest is missing. Run update-bayios.ps1 first.'
    }

    # Remove only containers belonging to the BayiOS project that were created
    # by another compose tool (for example bayios-app-1 vs bayios_app_1).
    Stop-BayiosForeignContainers -ProjectName $ProjectName

    $health = Get-BayiosHealth -Port $port
    if ($health.Json -and $health.Json.status -eq 'ok' -and $health.Json.migrations -and $health.Json.migrations.status -eq 'ok') {
        Write-BayiosLog ('BayiOS is already healthy on port {0}.' -f $port) 'OK'
        return
    }

    Write-BayiosLog 'Starting BayiOS containers ...'
    Invoke-BayiosCompose -ComposeFile $ComposeFile -Arguments @('up', '-d') | Out-Null

    $health = Wait-BayiosHealth -Port $port -TimeoutSeconds $TimeoutSeconds
    $healthy = ($health -and $health.Json -and $health.Json.status -eq 'ok' -and
        $health.Json.migrations -and $health.Json.migrations.status -eq 'ok')

    if (-not $healthy) {
        $detail = 'health did not become ready'
        if ($health -and $health.Error) { $detail = $health.Error }
        elseif ($health -and $health.Body) { $detail = Protect-BayiosSecrets -Text $health.Body }
        throw ('BayiOS did not become healthy on port {0}: {1}' -f $port, $detail)
    }

    Write-BayiosLog ('BayiOS is healthy on port {0}.' -f $port) 'OK'
} catch {
    Write-BayiosLog $_.Exception.Message 'ERROR'
    Write-BayiosLog 'Start failed. Check logs with: podman-compose logs --tail=100 app' 'ERROR'
    exit 1
} finally {
    Remove-BayiosLock -Lock $lock
}
