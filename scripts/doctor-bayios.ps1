#requires -Version 5.1
# READ-ONLY BayiOS diagnostic report.
#
# Safety contract:
#   - This script only runs read-only commands (podman ps/images/volume/logs,
#     git status/log, HTTP GET /health).
#   - It never stops or removes containers, never removes volumes, never runs
#     docker/podman compose down, and never runs pg_dump/pg_restore/dropdb.
#   - It is safe to run on production while users are working.

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$ProjectName = 'bayios',
    [string]$ComposeFile = '',
    [int]$Port = 0,
    [string]$OutputPath = '',
    [switch]$IncludeLogs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'Bayios.Common.psm1') -Force

$root = Get-BayiosRepoRoot -RepoPath $RepoPath
if ([string]::IsNullOrWhiteSpace($ComposeFile)) {
    $ComposeFile = Join-Path $root 'compose.yaml'
}
$port = Get-BayiosPort -RepoPath $root -Port $Port

$script:ReportLines = New-Object 'System.Collections.Generic.List[string]'

function Add-ReportLine {
    param([string]$Text = '')
    $script:ReportLines.Add($Text) | Out-Null
    Write-Host $Text
}

function Add-Section {
    param([string]$Title)
    Add-ReportLine ''
    Add-ReportLine ('=== {0} ===' -f $Title)
}

Add-ReportLine 'BayiOS diagnostic report (READ-ONLY)'
Add-ReportLine ('Generated: {0}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))
Add-ReportLine ('Computer: {0}' -f $env:COMPUTERNAME)
Add-ReportLine ('User: {0}' -f $env:USERNAME)
Add-ReportLine ('PowerShell: {0}' -f $PSVersionTable.PSVersion.ToString())
Add-ReportLine ('OS: {0}' -f [System.Environment]::OSVersion.VersionString)
Add-ReportLine ('Repo: {0}' -f $root)
Add-ReportLine ('Project: {0}' -f $ProjectName)
Add-ReportLine ('Compose file: {0}' -f $ComposeFile)
Add-ReportLine ('HTTP port: {0}' -f $port)
Add-ReportLine ''
Add-ReportLine 'This report does not modify containers, volumes, or databases.'

Add-Section 'Commands'
foreach ($command in @('podman', 'podman-compose', 'git', 'powershell')) {
    $found = Get-Command $command -ErrorAction SilentlyContinue
    if ($found) {
        Add-ReportLine ('{0}: {1}' -f $command, $found.Source)
    } else {
        Add-ReportLine ('{0}: NOT FOUND' -f $command)
    }
}

if (Get-Command podman -ErrorAction SilentlyContinue) {
    $version = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('--version')
    Add-ReportLine ('podman --version: {0}' -f $version.Output.Trim())

    $info = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('info', '--format', '{{.Host.OS}} / {{.Version.Version}}')
    Add-ReportLine ('podman info: {0}' -f $info.Output.Trim())
}

if (Get-Command podman-compose -ErrorAction SilentlyContinue) {
    $composeVersion = Invoke-BayiosCapture -FilePath 'podman-compose' -Arguments @('--version')
    Add-ReportLine ('podman-compose --version: {0}' -f $composeVersion.Output.Trim())
}

Add-Section 'All podman containers'
try {
    $ps = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
        'ps', '-a', '--format', '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}'
    )
    if ($ps.ExitCode -eq 0) {
        foreach ($line in ($ps.Output -split [Environment]::NewLine)) {
            if (-not [string]::IsNullOrWhiteSpace($line)) { Add-ReportLine $line }
        }
    } else {
        Add-ReportLine ('podman ps failed: {0}' -f $ps.Output)
    }
} catch {
    Add-ReportLine ('podman ps failed: {0}' -f $_.Exception.Message)
}

Add-Section 'BayiOS project containers (label com.docker.compose.project)'
try {
    $containers = @(Get-BayiosProjectContainers -ProjectName $ProjectName)
    if ($containers.Count -eq 0) {
        Add-ReportLine '(none)'
    } else {
        foreach ($container in $containers) {
            Add-ReportLine ('{0} | service={1} | oneoff={2} | image={3} | {4}' -f
                $container.Name, $container.Service, $container.OneOff, $container.Image, $container.Status)
        }

        $foreign = @($containers | Where-Object {
            $_.Name -ne ('{0}_app_1' -f $ProjectName) -and
            $_.Name -ne ('{0}_postgres_1' -f $ProjectName)
        })
        if ($foreign.Count -gt 0) {
            Add-ReportLine ''
            Add-ReportLine 'WARNING: foreign/duplicate naming detected. This is the usual cause of "two apps" and stale code:'
            foreach ($item in $foreign) {
                Add-ReportLine ('  foreign: {0}' -f $item.Name)
            }
            Add-ReportLine 'Run update-bayios.ps1 or start-bayios.ps1; they stop only BayiOS project containers before recreating.'
        }
    }
} catch {
    Add-ReportLine ('project container query failed: {0}' -f $_.Exception.Message)
}

Add-Section 'BayiOS images'
try {
    $images = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
        'images', '--format', '{{.Repository}}:{{.Tag}}|{{.ID}}|{{.Created}}'
    )
    if ($images.ExitCode -eq 0) {
        $rows = @($images.Output -split [Environment]::NewLine | Where-Object { $_ -match 'bayios' })
        if ($rows.Count -eq 0) {
            Add-ReportLine '(no bayios images)'
        } else {
            foreach ($row in $rows) { Add-ReportLine $row }
        }
    } else {
        Add-ReportLine ('podman images failed: {0}' -f $images.Output)
    }
} catch {
    Add-ReportLine ('podman images failed: {0}' -f $_.Exception.Message)
}

Add-Section 'BayiOS volumes'
try {
    $volumes = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('volume', 'ls', '--format', '{{.Name}}')
    if ($volumes.ExitCode -eq 0) {
        $rows = @($volumes.Output -split [Environment]::NewLine | Where-Object { $_ -match 'bayios' })
        if ($rows.Count -eq 0) {
            Add-ReportLine '(no bayios volumes)'
        } else {
            foreach ($row in $rows) { Add-ReportLine $row }
        }
    } else {
        Add-ReportLine ('podman volume ls failed: {0}' -f $volumes.Output)
    }
} catch {
    Add-ReportLine ('podman volume ls failed: {0}' -f $_.Exception.Message)
}

Add-Section ('Port {0} listeners' -f $port)
try {
    if ($env:OS -eq 'Windows_NT') {
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        if ($listeners.Count -eq 0) {
            Add-ReportLine '(no listener)'
        } else {
            foreach ($listener in $listeners) {
                $processName = '(unknown)'
                try {
                    $processName = (Get-Process -Id $listener.OwningProcess -ErrorAction Stop).ProcessName
                } catch { }
                Add-ReportLine ('{0}:{1} pid={2} process={3}' -f
                    $listener.LocalAddress, $listener.LocalPort, $listener.OwningProcess, $processName)
            }
        }
    } elseif (Get-Command ss -ErrorAction SilentlyContinue) {
        $ss = Invoke-BayiosCapture -FilePath 'ss' -Arguments @('-ltnp')
        $rows = @($ss.Output -split [Environment]::NewLine | Where-Object { $_ -match (':{0}\s' -f $port) })
        if ($rows.Count -eq 0) {
            Add-ReportLine '(no listener)'
        } else {
            foreach ($row in $rows) { Add-ReportLine $row.Trim() }
        }
    } else {
        Add-ReportLine '(port inspection not available on this OS)'
    }
} catch {
    Add-ReportLine ('port inspection failed: {0}' -f $_.Exception.Message)
}

Add-Section 'Health endpoint'
try {
    $health = Get-BayiosHealth -Port $port
    Add-ReportLine ('HTTP status: {0}' -f $health.StatusCode)
    if ($health.Error) {
        Add-ReportLine ('Error: {0}' -f $health.Error)
    }
    if ($health.Body) {
        Add-ReportLine (Protect-BayiosSecrets -Text $health.Body)
    }
} catch {
    Add-ReportLine ('health request failed: {0}' -f $_.Exception.Message)
}

Add-Section 'Git'
try {
    $git = Get-BayiosGitInfo -RepoPath $root
    Add-ReportLine ('branch: {0}' -f $git.Branch)
    Add-ReportLine ('commit: {0}' -f $git.Commit)
    Add-ReportLine ('working tree clean: {0}' -f $git.IsClean)
    if (-not [string]::IsNullOrWhiteSpace($git.StatusText)) {
        Add-ReportLine 'git status --porcelain:'
        foreach ($line in ($git.StatusText -split [Environment]::NewLine)) {
            if (-not [string]::IsNullOrWhiteSpace($line)) { Add-ReportLine ('  {0}' -f $line) }
        }
    }

    $remote = Invoke-BayiosCapture -FilePath 'git' -Arguments @('-C', $root, 'remote', '-v')
    if ($remote.ExitCode -eq 0) {
        foreach ($line in ($remote.Output -split [Environment]::NewLine)) {
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Add-ReportLine ('remote: {0}' -f ($line -replace '://[^/@]+@', '://***@'))
            }
        }
    }
} catch {
    Add-ReportLine ('git inspection failed: {0}' -f $_.Exception.Message)
}

Add-Section 'Configuration files (keys only, no secret values)'
try {
    if (Test-Path -LiteralPath $ComposeFile) {
        Add-ReportLine ('compose.yaml exists: yes')
        $matches = @(Select-String -LiteralPath $ComposeFile -Pattern '^\s*(name|image|build|context):' -ErrorAction SilentlyContinue)
        foreach ($match in $matches) {
            Add-ReportLine ('  {0}' -f $match.Line.Trim())
        }
    } else {
        Add-ReportLine ('compose.yaml exists: NO')
    }

    $envPath = Join-Path $root '.env'
    if (Test-Path -LiteralPath $envPath) {
        Add-ReportLine '.env exists: yes'
        $keys = @(Get-Content -LiteralPath $envPath -Encoding UTF8 | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
                ($line -split '=', 2)[0].Trim()
            }
        })
        Add-ReportLine ('  keys: {0}' -f (($keys | Sort-Object -Unique) -join ', '))
        Add-ReportLine ('  POSTGRES_PASSWORD present: {0}' -f ($keys -contains 'POSTGRES_PASSWORD'))
    } else {
        Add-ReportLine '.env exists: NO'
    }
} catch {
    Add-ReportLine ('configuration inspection failed: {0}' -f $_.Exception.Message)
}

Add-Section 'Scheduled tasks'
try {
    if ($env:OS -eq 'Windows_NT') {
        $tasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
            $_.TaskName -like '*BayiOS*' -or $_.TaskName -like '*Bayios*'
        })
        if ($tasks.Count -eq 0) {
            Add-ReportLine '(no BayiOS scheduled task)'
        } else {
            foreach ($task in $tasks) {
                $info = $null
                try { $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -ErrorAction Stop } catch { }
                Add-ReportLine ('{0} | state={1} | last={2} | result={3}' -f
                    $task.TaskName, $task.State,
                    $(if ($info) { $info.LastRunTime } else { 'unknown' }),
                    $(if ($info) { $info.LastTaskResult } else { 'unknown' }))
            }
        }
    } else {
        Add-ReportLine '(Windows Task Scheduler not available on this OS)'
    }
} catch {
    Add-ReportLine ('scheduled task inspection failed: {0}' -f $_.Exception.Message)
}

Add-Section 'Disk space'
foreach ($path in @($root, (Join-Path $root 'backups'))) {
    $free = Get-BayiosDiskFreeGB -Path $path
    if ($null -eq $free) {
        Add-ReportLine ('{0}: unknown' -f $path)
    } else {
        Add-ReportLine ('{0}: {1:N2} GiB free' -f $path, $free)
    }
}

if ($IncludeLogs) {
    Add-Section 'App logs (last 40 lines)'
    try {
        $app = Get-BayiosServiceContainer -ProjectName $ProjectName -Service 'app'
        if ($app) {
            $logs = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('logs', '--tail', '40', $app.Name)
            foreach ($line in ($logs.Output -split [Environment]::NewLine)) {
                Add-ReportLine (Protect-BayiosSecrets -Text $line)
            }
        } else {
            Add-ReportLine '(app container not found)'
        }
    } catch {
        Add-ReportLine ('log inspection failed: {0}' -f $_.Exception.Message)
    }
}

Add-Section 'Script files'
foreach ($name in @('start-bayios.ps1', 'update-bayios.ps1', 'backup-bayios.ps1', 'doctor-bayios.ps1', 'stop-bayios.ps1', 'shutdown-bayios.ps1', 'install-bayios-tasks.ps1', 'install-shutdown-task.ps1')) {
    $path = Join-Path $PSScriptRoot $name
    Add-ReportLine ('{0}: {1}' -f $name, $(if (Test-Path -LiteralPath $path) { 'present' } else { 'missing' }))
}

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $reportDir = Join-Path $root 'reports'
    if (-not (Test-Path -LiteralPath $reportDir)) {
        New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
    }
    $OutputPath = Join-Path $reportDir ('bayios-doctor-{0}.txt' -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
}

$text = $script:ReportLines -join [Environment]::NewLine
Set-Content -LiteralPath $OutputPath -Value $text -Encoding UTF8
Write-Host ''
Write-Host ('Report written: {0}' -f $OutputPath) -ForegroundColor Green
