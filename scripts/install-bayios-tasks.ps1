#requires -Version 5.1
# Registers the BayiOS Windows Task Scheduler entries:
#   - "BayiOS Autostart": runs start-bayios.ps1 at user logon (with a delay).
#   - "BayiOS Backup": optional daily backup before the laptop is usually closed.
#
# Uses the current Windows user because rootless Podman is per-user.
# Run this once from an elevated or normal PowerShell window; it does not need
# administrator rights for a user logon task in most setups.

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$TaskUser = '',
    [int]$DelayMinutes = 2,
    [string]$BackupTime = '19:30',
    [switch]$SkipBackup,
    [switch]$Remove
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'install-bayios-tasks.ps1 is Windows-only.'
}

Import-Module (Join-Path $PSScriptRoot 'Bayios.Common.psm1') -Force

$root = Get-BayiosRepoRoot -RepoPath $RepoPath
if ([string]::IsNullOrWhiteSpace($TaskUser)) {
    $TaskUser = '{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME
}

$autostartName = 'BayiOS Autostart'
$backupName = 'BayiOS Backup'
$startScript = Join-Path $PSScriptRoot 'start-bayios.ps1'
$backupScript = Join-Path $PSScriptRoot 'backup-bayios.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

if ($Remove) {
    foreach ($name in @($autostartName, $backupName)) {
        $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-BayiosLog ('Removed scheduled task: {0}' -f $name) 'OK'
        }
    }
    return
}

foreach ($path in @($startScript, $backupScript, $powershell)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw ('Required file not found: {0}' -f $path)
    }
}

$commonSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$startAction = New-ScheduledTaskAction -Execute $powershell `
    -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $startScript) `
    -WorkingDirectory $root
$startTrigger = New-ScheduledTaskTrigger -AtLogOn -User $TaskUser
$startTrigger.Delay = 'PT{0}M' -f $DelayMinutes

Register-ScheduledTask -TaskName $autostartName -Action $startAction -Trigger $startTrigger `
    -Settings $commonSettings -Description 'Starts BayiOS with rootless Podman at user logon.' -Force | Out-Null
Write-BayiosLog ('Registered scheduled task: {0} (delay {1} min)' -f $autostartName, $DelayMinutes) 'OK'

if (-not $SkipBackup) {
    $backupAction = New-ScheduledTaskAction -Execute $powershell `
        -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $backupScript) `
        -WorkingDirectory $root
    $backupTrigger = New-ScheduledTaskTrigger -Daily -At $BackupTime

    Register-ScheduledTask -TaskName $backupName -Action $backupAction -Trigger $backupTrigger `
        -Settings $commonSettings -Description 'Daily BayiOS PostgreSQL backup.' -Force | Out-Null
    Write-BayiosLog ('Registered scheduled task: {0} (daily at {1})' -f $backupName, $BackupTime) 'OK'
}

Write-BayiosLog 'Task registration complete. Check with: Get-ScheduledTask | Where-Object TaskName -like "*BayiOS*"' 'OK'
