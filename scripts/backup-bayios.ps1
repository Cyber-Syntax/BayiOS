#requires -Version 5.1
# Native Windows/PowerShell database backup for BayiOS.
# Uses pg_dump inside the running postgres container and copies the dump to the
# host. It NEVER drops/creates a database, never restores into production, and
# never removes containers or volumes.

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$ProjectName = 'bayios',
    [string]$ComposeFile = '',
    [string]$BackupDir = '',
    [string]$ExternalBackupDir = '',
    [int]$RetentionDaily = 14,
    [int]$RetentionWeekly = 8,
    [int]$RetentionMonthly = 12,
    [switch]$NoStartPostgres
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Bayios.Common.psm1') -Force

$root = Get-BayiosRepoRoot -RepoPath $RepoPath
if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
    $ComposeFile = Join-Path $root 'compose.yaml'
}
if ([string]::IsNullOrWhiteSpace($BackupDir)) {
    $BackupDir = Join-Path $root 'backups'
}

$null = Start-BayiosLog -RepoPath $root -Action 'backup'
$lock = $null

try {
    $lock = New-BayiosLock -RepoPath $root

    Start-BayiosPodmanMachine -TimeoutSeconds 180
    Assert-BayiosPrerequisites -RepoPath $root -ComposeFile $ComposeFile

    $result = Invoke-BayiosBackup -RepoPath $root -ComposeFile $ComposeFile `
        -ProjectName $ProjectName -BackupDir $BackupDir `
        -ExternalBackupDir $ExternalBackupDir `
        -RetentionDaily $RetentionDaily -RetentionWeekly $RetentionWeekly `
        -RetentionMonthly $RetentionMonthly -NoStartPostgres:$NoStartPostgres

    Write-BayiosLog ('Backup OK: {0} ({1:N2} MiB)' -f $result.DailyPath, ($result.SizeBytes / 1MB)) 'OK'
    Write-BayiosLog ('Weekly copy: {0}' -f $result.WeeklyPath)
    Write-BayiosLog ('Monthly copy: {0}' -f $result.MonthlyPath)
    Write-BayiosLog ('Old backup files removed by retention: {0}' -f $result.DeletedOldFiles)
} catch {
    Write-BayiosLog $_.Exception.Message 'ERROR'
    Write-BayiosLog 'Backup failed. The production database was not modified.' 'ERROR'
    exit 1
} finally {
    Remove-BayiosLock -Lock $lock
}
