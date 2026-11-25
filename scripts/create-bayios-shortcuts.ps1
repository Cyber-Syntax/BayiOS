#requires -Version 5.1
# Creates desktop shortcuts for the BayiOS operational scripts.
# Windows-only. No database, container, or volume operation is performed here.

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$DesktopPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'create-bayios-shortcuts.ps1 is Windows-only.'
}

Import-Module (Join-Path $PSScriptRoot 'Bayios.Common.psm1') -Force

$root = Get-BayiosRepoRoot -RepoPath $RepoPath
if ([string]::IsNullOrWhiteSpace($DesktopPath)) {
    $DesktopPath = [Environment]::GetFolderPath('Desktop')
}
if (-not (Test-Path -LiteralPath $DesktopPath)) {
    throw ('Desktop directory not found: {0}' -f $DesktopPath)
}

$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shell = New-Object -ComObject WScript.Shell

$items = @(
    @{ Name = 'BayiOS Baslat'; Script = 'start-bayios.ps1'; Description = 'Starts BayiOS (existing image).' },
    @{ Name = 'BayiOS Guncelle'; Script = 'update-bayios.ps1'; Description = 'Builds and deploys the current BayiOS code.' },
    @{ Name = 'BayiOS Yedek'; Script = 'backup-bayios.ps1'; Description = 'Takes a PostgreSQL backup.' },
    @{ Name = 'BayiOS Rapor'; Script = 'doctor-bayios.ps1'; Description = 'Produces a read-only diagnostic report.' }
)

foreach ($item in $items) {
    $scriptPath = Join-Path $PSScriptRoot $item.Script
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        Write-BayiosLog ('Skipping missing script: {0}' -f $scriptPath) 'WARN'
        continue
    }

    $shortcutPath = Join-Path $DesktopPath ('{0}.lnk' -f $item.Name)
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $scriptPath
    $shortcut.WorkingDirectory = $root
    $shortcut.IconLocation = '{0},0' -f $powershell
    $shortcut.Description = $item.Description
    $shortcut.Save()
    Write-BayiosLog ('Created shortcut: {0}' -f $shortcutPath) 'OK'
}

Write-BayiosLog 'Desktop shortcuts created.' 'OK'
