#requires -Version 5.1
# Installs a Local Group Policy USER logoff script that stops BayiOS before
# Windows logs off/shuts down. User logoff scripts run as the logged-on user,
# which is required because Podman is rootless and per-user.
#
# This is intentionally NOT a Task Scheduler "event 1074" task: Task Scheduler
# does not wait for the task during shutdown. A user logoff script is executed
# synchronously by Windows while the user profile is still available.
#
# Run this script as Administrator. It modifies:
#   %SystemRoot%\System32\GroupPolicy\User\Scripts\scripts.ini
# and creates a timestamped .bak copy first.

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [switch]$Remove,
    [switch]$NoMachineStop
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'install-shutdown-task.ps1 is Windows-only.'
}

$principal = New-Object Security.Principal.WindowsPrincipal -ArgumentList ([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as Administrator (right-click PowerShell -> Run as administrator).'
}

Import-Module (Join-Path $PSScriptRoot 'Bayios.Common.psm1') -Force

$root = Get-BayiosRepoRoot -RepoPath $RepoPath
$null = Start-BayiosLog -RepoPath $root -Action 'shutdown-task'

$scriptsIni = Join-Path $env:SystemRoot 'System32\GroupPolicy\User\Scripts\scripts.ini'
$stopScript = Join-Path $PSScriptRoot 'stop-bayios.ps1'
$powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$gpupdateExe = Join-Path $env:SystemRoot 'System32\gpupdate.exe'

if (-not $Remove -and -not (Test-Path -LiteralPath $stopScript)) {
    throw ('Required script not found: {0}' -f $stopScript)
}

function Read-ScriptsIni {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return @('[Logoff]')
    }

    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $isUnicode = ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE)
    if ($isUnicode) {
        $text = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::Unicode)
    } else {
        $text = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::Default)
    }

    return @($text -split ([char]10) | ForEach-Object { $_.TrimEnd([char]13) })
}

function Write-ScriptsIni {
    param([string]$Path, [string[]]$Lines)

    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $text = ($Lines -join [Environment]::NewLine) + [Environment]::NewLine
    [System.IO.File]::WriteAllText($Path, $text, [System.Text.Encoding]::Unicode)
}

function Get-SectionRange {
    param([string[]]$Lines, [string]$Section)

    $start = -1
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim() -ieq $Section) {
            $start = $i
            break
        }
    }
    if ($start -lt 0) { return $null }

    $end = $Lines.Count
    for ($i = $start + 1; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].Trim().StartsWith('[')) {
            $end = $i
            break
        }
    }

    return [pscustomobject]@{ Start = $start; End = $end }
}

function Get-LogoffEntries {
    param([string[]]$Lines, [int]$Start, [int]$End)

    $entries = @()
    for ($i = $Start + 1; $i -lt $End; $i++) {
        if ($Lines[$i] -match '^\s*(\d+)CmdLine=(.*)$') {
            $index = [int]$matches[1]
            $command = $matches[2]
            $parameters = ''

            $parameterPattern = '^\s*{0}Parameters=(.*)$' -f $index
            for ($j = $i + 1; $j -lt $End; $j++) {
                if ($Lines[$j] -match $parameterPattern) {
                    $parameters = $matches[1]
                    break
                }
            }

            $entries += [pscustomobject]@{
                Index      = $index
                CmdLine    = $command
                Parameters = $parameters
            }
        }
    }

    return $entries
}

$lines = @(Read-ScriptsIni -Path $scriptsIni)
$range = Get-SectionRange -Lines $lines -Section '[Logoff]'

if ($null -eq $range) {
    $lines += ''
    $lines += '[Logoff]'
    $range = Get-SectionRange -Lines $lines -Section '[Logoff]'
}

$entries = @(Get-LogoffEntries -Lines $lines -Start $range.Start -End $range.End)
$entries = @($entries | Where-Object { $_.CmdLine -notmatch 'stop-bayios\.ps1' -and $_.Parameters -notmatch 'stop-bayios\.ps1' })

if (-not $Remove) {
    $parameters = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $stopScript
    if (-not $NoMachineStop) {
        $parameters += ' -StopMachine'
    }

    $entries += [pscustomobject]@{
        CmdLine    = $powershellExe
        Parameters = $parameters
    }
}

$newSection = @('[Logoff]')
$index = 0
foreach ($entry in $entries) {
    $newSection += ('{0}CmdLine={1}' -f $index, $entry.CmdLine)
    $newSection += ('{0}Parameters={1}' -f $index, $entry.Parameters)
    $index++
}

$before = @()
if ($range.Start -gt 0) { $before = $lines[0..($range.Start - 1)] }
$after = @()
if ($range.End -lt $lines.Count) { $after = $lines[$range.End..($lines.Count - 1)] }

$newLines = @($before) + @($newSection) + @($after)

if (Test-Path -LiteralPath $scriptsIni) {
    $backup = '{0}.bak-{1}' -f $scriptsIni, (Get-Date -Format 'yyyyMMdd_HHmmss')
    Copy-Item -LiteralPath $scriptsIni -Destination $backup -Force
    Write-BayiosLog ('Backup: {0}' -f $backup)
}

Write-ScriptsIni -Path $scriptsIni -Lines $newLines
Write-BayiosLog ('Updated user logoff script: {0}' -f $scriptsIni) 'OK'

if (Test-Path -LiteralPath $gpupdateExe) {
    $gpupdateOutput = & $gpupdateExe /force 2>&1
    Write-BayiosLog (($gpupdateOutput | Out-String).Trim())
    if ($LASTEXITCODE -ne 0) {
        Write-BayiosLog ('gpupdate exited with code {0}; logout script will be used after the next Group Policy refresh.' -f $LASTEXITCODE) 'WARN'
    }
}

if ($Remove) {
    Write-BayiosLog 'BayiOS user logoff script removed.' 'OK'
} else {
    Write-BayiosLog 'BayiOS user logoff script installed.' 'OK'
    Write-BayiosLog 'Test it by logging off or shutting down; check logs\bayios-stop-*.log afterwards.' 'WARN'
    Write-BayiosLog 'If the log is missing, disable Windows Fast Startup and test again; the desktop "BayiOS Kapat ve PC Kapat" shortcut is the guaranteed fallback.' 'WARN'
}
