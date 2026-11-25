#requires -Version 5.1
# Shared helpers for the BayiOS Windows/PowerShell operational scripts.
# All messages are ASCII-only so Windows PowerShell 5.1 can read this file
# without a UTF-8 BOM. Logs and comments are English; user-facing app text stays
# Turkish in the application itself.

Set-StrictMode -Version Latest

$script:BayiosLogFile = $null

function Write-BayiosLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet('INFO', 'OK', 'WARN', 'ERROR')][string]$Level = 'INFO'
    )

    $line = '[{0}] [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    $color = switch ($Level) {
        'OK' { 'Green' }
        'WARN' { 'Yellow' }
        'ERROR' { 'Red' }
        default { 'Gray' }
    }
    Write-Host $line -ForegroundColor $color

    if ($script:BayiosLogFile) {
        try {
            Add-Content -LiteralPath $script:BayiosLogFile -Value $line -Encoding UTF8
        } catch {
            # Logging must never hide the real operation result.
        }
    }
}

function Set-BayiosLogFile {
    param([Parameter(Mandatory = $true)][string]$Path)
    $script:BayiosLogFile = $Path
}

function Start-BayiosLog {
    param(
        [Parameter(Mandatory = $true)][string]$RepoPath,
        [Parameter(Mandatory = $true)][string]$Action
    )

    $logDir = Join-Path $RepoPath 'logs'
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $path = Join-Path $logDir ('bayios-{0}-{1}.log' -f $Action, $stamp)
    Set-BayiosLogFile -Path $path
    Write-BayiosLog ('Log file: {0}' -f $path)
    return $path
}

function Get-BayiosRepoRoot {
    param([string]$RepoPath = '')

    if (-not [string]::IsNullOrWhiteSpace($RepoPath)) {
        return (Resolve-Path -LiteralPath $RepoPath -ErrorAction Stop).Path
    }

    # This module lives in <repo>/scripts.
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..') -ErrorAction Stop).Path
}

function Get-BayiosDotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$RepoPath,
        [Parameter(Mandatory = $true)][string]$Key
    )

    $path = Join-Path $RepoPath '.env'
    if (-not (Test-Path -LiteralPath $path)) {
        return $null
    }

    foreach ($line in (Get-Content -LiteralPath $path -Encoding UTF8)) {
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith('#')) { continue }

        $index = $trim.IndexOf('=')
        if ($index -lt 1) { continue }

        $name = $trim.Substring(0, $index).Trim()
        if ($name -ne $Key) { continue }

        $value = $trim.Substring($index + 1).Trim()
        if ($value.Length -ge 2) {
            $first = $value.Substring(0, 1)
            $last = $value.Substring($value.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        return $value
    }

    return $null
}

function Test-BayiosCommand {
    param([Parameter(Mandatory = $true)][string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-BayiosCapture {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $global:LASTEXITCODE = 0
        $output = & $FilePath @Arguments 2>&1
        $code = $LASTEXITCODE
    } catch {
        $ErrorActionPreference = $previous
        return [pscustomobject]@{
            ExitCode = 127
            Output   = $_.Exception.Message
        }
    } finally {
        $ErrorActionPreference = $previous
    }

    $text = ($output | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $_.ToString()
        } else {
            [string]$_
        }
    }) -join "`n"

    return [pscustomobject]@{
        ExitCode = $code
        Output   = $text
    }
}

function Assert-BayiosPrerequisites {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepoPath,
        [Parameter(Mandatory = $true)][string]$ComposeFile,
        [switch]$RequireGit
    )

    # Task Scheduler sometimes starts with a PATH that does not include uv's
    # tool directory. Add it before failing on a missing podman-compose.
    if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        $uvBin = Join-Path $env:USERPROFILE '.local\bin'
        if (Test-Path -LiteralPath $uvBin) {
            $env:Path = '{0};{1}' -f $uvBin, $env:Path
        }
    }

    foreach ($command in @('podman', 'podman-compose')) {
        if (-not (Test-BayiosCommand -Name $command)) {
            throw ('Required command not found: {0}' -f $command)
        }
    }

    if ($RequireGit -and -not (Test-BayiosCommand -Name 'git')) {
        throw 'Required command not found: git'
    }

    if (-not (Test-Path -LiteralPath $ComposeFile)) {
        throw ('Compose file not found: {0}' -f $ComposeFile)
    }

    if (-not (Test-Path -LiteralPath (Join-Path $RepoPath '.env'))) {
        Write-BayiosLog ('.env not found at {0}; compose will fail if POSTGRES_PASSWORD is missing.' -f $RepoPath) 'WARN'
    }

    $info = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('info', '--format', '{{.Host.OS}}')
    if ($info.ExitCode -ne 0) {
        throw ('podman info failed: {0}' -f $info.Output)
    }

    $composeVersion = Invoke-BayiosCapture -FilePath 'podman-compose' -Arguments @('--version')
    if ($composeVersion.ExitCode -ne 0) {
        throw ('podman-compose is not usable: {0}' -f $composeVersion.Output)
    }
}

function Start-BayiosPodmanMachine {
    [CmdletBinding()]
    param([int]$TimeoutSeconds = 180)

    if ($env:OS -ne 'Windows_NT') {
        return
    }

    if (-not (Test-BayiosCommand -Name 'podman')) {
        throw 'Required command not found: podman'
    }

    $info = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('info', '--format', '{{.Host.OS}}')
    if ($info.ExitCode -eq 0) {
        return
    }

    Write-BayiosLog 'Podman machine is not reachable; starting it.' 'WARN'
    $null = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('machine', 'start')

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $info = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('info', '--format', '{{.Host.OS}}')
        if ($info.ExitCode -eq 0) {
            Write-BayiosLog 'Podman machine is ready.' 'OK'
            return
        }
        Start-Sleep -Seconds 3
    }

    throw ('Podman machine did not become ready within {0} seconds.' -f $TimeoutSeconds)
}

function Invoke-BayiosCompose {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ComposeFile,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $composeArgs = @('-f', $ComposeFile) + $Arguments
    Write-BayiosLog ('podman-compose {0}' -f ($Arguments -join ' '))
    $result = Invoke-BayiosCapture -FilePath 'podman-compose' -Arguments $composeArgs

    foreach ($line in ($result.Output -split "`r?`n")) {
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            Write-Host $line
        }
    }

    if ($result.ExitCode -ne 0) {
        throw ('podman-compose {0} failed with exit code {1}' -f ($Arguments -join ' '), $result.ExitCode)
    }

    return $result
}

function Invoke-BayiosComposeCapture {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ComposeFile,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    $composeArgs = @('-f', $ComposeFile) + $Arguments
    return Invoke-BayiosCapture -FilePath 'podman-compose' -Arguments $composeArgs
}

function Get-BayiosProjectContainers {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$ProjectName)

    $format = '{{.Names}}|{{.Label "com.docker.compose.service"}}|{{.Label "com.docker.compose.oneoff"}}|{{.Status}}|{{.Image}}'
    $result = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
        'ps', '-a',
        '--filter', ('label=com.docker.compose.project={0}' -f $ProjectName),
        '--format', $format
    )

    if ($result.ExitCode -ne 0) {
        throw ('podman ps failed: {0}' -f $result.Output)
    }

    $containers = @()
    foreach ($line in ($result.Output -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split '\|', 5
        if ($parts.Count -lt 5) { continue }
        $containers += [pscustomobject]@{
            Name    = $parts[0].Trim()
            Service = $parts[1].Trim()
            OneOff  = $parts[2].Trim()
            Status  = $parts[3].Trim()
            Image   = $parts[4].Trim()
        }
    }

    return $containers
}

function Get-BayiosServiceContainer {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ProjectName,
        [Parameter(Mandatory = $true)][string]$Service
    )

    $containers = @(Get-BayiosProjectContainers -ProjectName $ProjectName |
        Where-Object { $_.Service -eq $Service -and $_.OneOff -ne 'True' })

    if ($containers.Count -eq 0) { return $null }

    $running = @($containers | Where-Object { $_.Status -match '^Up' })
    if ($running.Count -eq 1) { return $running[0] }
    if ($running.Count -gt 1) {
        $names = ($running | ForEach-Object { $_.Name }) -join ', '
        throw ('Multiple running containers found for service {0}: {1}' -f $Service, $names)
    }

    # No running container: return a stopped one so callers can start it.
    return $containers[0]
}

function Stop-BayiosForeignContainers {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ProjectName,
        [switch]$WhatIfOnly
    )

    $containers = @(Get-BayiosProjectContainers -ProjectName $ProjectName)
    if ($containers.Count -eq 0) { return }

    $expectedNames = @(
        ('{0}_app_1' -f $ProjectName),
        ('{0}_postgres_1' -f $ProjectName)
    )

    $foreignNames = @()
    foreach ($container in $containers) {
        if ($expectedNames -notcontains $container.Name) {
            $foreignNames += $container.Name
        }
    }

    foreach ($service in @('app', 'postgres')) {
        $matches = @($containers | Where-Object { $_.Service -eq $service -and $_.OneOff -ne 'True' })
        if ($matches.Count -gt 1) {
            $expected = '{0}_{1}_1' -f $ProjectName, $service
            foreach ($match in $matches) {
                if ($match.Name -ne $expected -and $foreignNames -notcontains $match.Name) {
                    $foreignNames += $match.Name
                }
            }
        }
    }

    foreach ($name in $foreignNames) {
        if ($WhatIfOnly) {
            Write-BayiosLog ('[WhatIf] would stop/remove foreign container {0}' -f $name) 'WARN'
            continue
        }

        Write-BayiosLog ('Stopping foreign/duplicate BayiOS container: {0}' -f $name) 'WARN'
        $null = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('stop', '-t', '30', $name)
        $remove = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('rm', '-f', $name)
        if ($remove.ExitCode -ne 0) {
            Write-BayiosLog ('Could not remove {0}: {1}' -f $name, $remove.Output) 'WARN'
        }
    }
}

function Get-BayiosImageId {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Image)

    $result = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('image', 'inspect', '--format', '{{.Id}}', $Image)
    if ($result.ExitCode -ne 0) { return $null }
    return $result.Output.Trim()
}

function Get-BayiosContainerImageId {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$ContainerName)

    $result = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('inspect', '--format', '{{.Image}}', $ContainerName)
    if ($result.ExitCode -ne 0) { return $null }
    return $result.Output.Trim()
}

function Get-BayiosHealth {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutMilliseconds = 3000
    )

    $uri = 'http://127.0.0.1:{0}/health' -f $Port
    $request = [System.Net.WebRequest]::Create($uri)
    $request.Method = 'GET'
    $request.Timeout = $TimeoutMilliseconds
    $request.Proxy = $null

    $statusCode = 0
    $body = $null
    $errorMessage = $null

    try {
        $response = $request.GetResponse()
        $statusCode = [int]$response.StatusCode
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        $body = $reader.ReadToEnd()
        $reader.Close()
        $response.Close()
    } catch [System.Net.WebException] {
        $webResponse = $_.Exception.Response
        if ($webResponse) {
            $statusCode = [int]$webResponse.StatusCode
            $reader = New-Object System.IO.StreamReader($webResponse.GetResponseStream())
            $body = $reader.ReadToEnd()
            $reader.Close()
            $webResponse.Close()
        } else {
            $errorMessage = $_.Exception.Message
        }
    } catch {
        $errorMessage = $_.Exception.Message
    }

    $json = $null
    if (-not [string]::IsNullOrWhiteSpace($body)) {
        try { $json = $body | ConvertFrom-Json } catch { }
    }

    return [pscustomobject]@{
        StatusCode = $statusCode
        Body       = $body
        Json       = $json
        Error      = $errorMessage
    }
}

function Wait-BayiosHealth {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 240,
        [bool]$RequireMigrations = $true
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = $null

    while ((Get-Date) -lt $deadline) {
        $last = Get-BayiosHealth -Port $Port
        if ($last.Json -and $last.Json.status -eq 'ok') {
            if (-not $RequireMigrations) { return $last }
            if ($last.Json.migrations -and $last.Json.migrations.status -eq 'ok') { return $last }
        }
        Start-Sleep -Seconds 2
    }

    return $last
}

function Get-BayiosPort {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepoPath,
        [int]$Port = 0
    )

    if ($Port -gt 0) { return $Port }

    $value = Get-BayiosDotEnvValue -RepoPath $RepoPath -Key 'BAYIOS_PORT'
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        $parsed = 0
        if ([int]::TryParse($value, [ref]$parsed)) { return $parsed }
    }

    return 8000
}

function Wait-BayiosPostgres {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ProjectName,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $postgres = Get-BayiosServiceContainer -ProjectName $ProjectName -Service 'postgres'
        if ($postgres -and $postgres.Status -match '^Up') {
            $ready = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
                'exec', $postgres.Name, 'pg_isready', '-U', 'bayios', '-d', 'bayios'
            )
            if ($ready.ExitCode -eq 0) { return $postgres }
        }
        Start-Sleep -Seconds 2
    }

    throw ('PostgreSQL did not become ready within {0} seconds.' -f $TimeoutSeconds)
}

function New-BayiosLock {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$RepoPath)

    $logDir = Join-Path $RepoPath 'logs'
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    $path = Join-Path $logDir '.bayios-operation.lock'
    try {
        $stream = [System.IO.File]::Open(
            $path,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
        return [pscustomobject]@{
            Path   = $path
            Stream = $stream
        }
    } catch [System.IO.IOException] {
        throw ('Another BayiOS operation is already running (lock: {0}).' -f $path)
    }
}

function Remove-BayiosLock {
    param($Lock)
    if ($Lock -and $Lock.Stream) {
        $Lock.Stream.Dispose()
    }
}

function Get-BayiosGitInfo {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$RepoPath)

    $branch = Invoke-BayiosCapture -FilePath 'git' -Arguments @('-C', $RepoPath, 'rev-parse', '--abbrev-ref', 'HEAD')
    $commit = Invoke-BayiosCapture -FilePath 'git' -Arguments @('-C', $RepoPath, 'rev-parse', '--short', 'HEAD')
    $status = Invoke-BayiosCapture -FilePath 'git' -Arguments @('-C', $RepoPath, 'status', '--porcelain')

    $branchValue = 'unknown'
    if ($branch.ExitCode -eq 0) { $branchValue = $branch.Output.Trim() }

    $commitValue = 'unknown'
    if ($commit.ExitCode -eq 0) { $commitValue = $commit.Output.Trim() }

    return [pscustomobject]@{
        Branch     = $branchValue
        Commit     = $commitValue
        IsClean    = ($status.ExitCode -eq 0 -and [string]::IsNullOrWhiteSpace($status.Output))
        StatusText = $status.Output.Trim()
    }
}

function Invoke-BayiosGitPull {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepoPath,
        [string]$Branch = ''
    )

    $status = Invoke-BayiosCapture -FilePath 'git' -Arguments @('-C', $RepoPath, 'status', '--porcelain')
    if ($status.ExitCode -ne 0) {
        throw ('git status failed: {0}' -f $status.Output)
    }
    if (-not [string]::IsNullOrWhiteSpace($status.Output)) {
        throw ('Git working tree is not clean. Commit or stash changes before updating:{0}{1}' -f "`n", $status.Output)
    }

    $fetch = Invoke-BayiosCapture -FilePath 'git' -Arguments @('-C', $RepoPath, 'fetch', 'origin')
    if ($fetch.ExitCode -ne 0) {
        throw ('git fetch failed: {0}' -f $fetch.Output)
    }

    if (-not [string]::IsNullOrWhiteSpace($Branch)) {
        $checkout = Invoke-BayiosCapture -FilePath 'git' -Arguments @('-C', $RepoPath, 'checkout', $Branch)
        if ($checkout.ExitCode -ne 0) {
            throw ('git checkout {0} failed: {1}' -f $Branch, $checkout.Output)
        }
        $pull = Invoke-BayiosCapture -FilePath 'git' -Arguments @('-C', $RepoPath, 'pull', '--ff-only', 'origin', $Branch)
    } else {
        $pull = Invoke-BayiosCapture -FilePath 'git' -Arguments @('-C', $RepoPath, 'pull', '--ff-only')
    }

    if ($pull.ExitCode -ne 0) {
        throw ('git pull --ff-only failed: {0}' -f $pull.Output)
    }

    Write-BayiosLog $pull.Output
}

function Get-BayiosDiskFreeGB {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Path)

    try {
        $full = [System.IO.Path]::GetFullPath($Path)
        $root = [System.IO.Path]::GetPathRoot($full)
        if ([string]::IsNullOrWhiteSpace($root)) { return $null }
        $drive = New-Object System.IO.DriveInfo($root)
        return [math]::Round($drive.AvailableFreeSpace / 1GB, 2)
    } catch {
        return $null
    }
}

function Protect-BayiosSecrets {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    return ($Text -replace 'postgresql\+psycopg://[^\s]+', 'postgresql+psycopg://***')
}

function Invoke-BayiosBackup {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RepoPath,
        [Parameter(Mandatory = $true)][string]$ComposeFile,
        [string]$ProjectName = 'bayios',
        [string]$BackupDir = '',
        [string]$ExternalBackupDir = '',
        [int]$RetentionDaily = 14,
        [int]$RetentionWeekly = 8,
        [int]$RetentionMonthly = 12,
        [switch]$NoStartPostgres
    )

    if ([string]::IsNullOrWhiteSpace($BackupDir)) {
        $BackupDir = Join-Path $RepoPath 'backups'
    }

    $daily = Join-Path $BackupDir 'daily'
    $weekly = Join-Path $BackupDir 'weekly'
    $monthly = Join-Path $BackupDir 'monthly'
    foreach ($directory in @($daily, $weekly, $monthly)) {
        if (-not (Test-Path -LiteralPath $directory)) {
            New-Item -ItemType Directory -Path $directory -Force | Out-Null
        }
    }

    $freeGB = Get-BayiosDiskFreeGB -Path $daily
    if ($null -ne $freeGB -and $freeGB -lt 1) {
        throw ('Less than 1 GiB free in {0} ({1} GiB).' -f $daily, $freeGB)
    }

    $postgres = Get-BayiosServiceContainer -ProjectName $ProjectName -Service 'postgres'
    if (-not $postgres -or $postgres.Status -notmatch '^Up') {
        if ($NoStartPostgres) {
            throw 'PostgreSQL is not running; start it before taking a backup.'
        }
        Write-BayiosLog 'PostgreSQL is not running; starting the postgres service only.' 'WARN'
        Invoke-BayiosCompose -ComposeFile $ComposeFile -Arguments @('up', '-d', 'postgres') | Out-Null
        $postgres = Wait-BayiosPostgres -ProjectName $ProjectName
    }

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $fileName = 'bayios_{0}.dump' -f $stamp
    $destination = Join-Path $daily $fileName
    $remotePath = '/tmp/{0}' -f $fileName

    Write-BayiosLog ('Dumping database bayios from container {0} ...' -f $postgres.Name)
    try {
        $dump = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
            'exec', $postgres.Name, 'pg_dump', '-U', 'bayios', '-d', 'bayios', '-Fc', '-f', $remotePath
        )
        if ($dump.ExitCode -ne 0) {
            throw ('pg_dump failed: {0}' -f $dump.Output)
        }

        # Validate the dump header without touching the production database.
        $verify = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
            'exec', $postgres.Name, 'pg_restore', '-l', '-f', '/dev/null', $remotePath
        )
        if ($verify.ExitCode -ne 0) {
            throw ('Dump verification failed: {0}' -f $verify.Output)
        }

        $copy = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
            'cp', ('{0}:{1}' -f $postgres.Name, $remotePath), $destination
        )
        if ($copy.ExitCode -ne 0) {
            throw ('podman cp failed: {0}' -f $copy.Output)
        }
    } finally {
        # Remove only the temporary dump file inside the container.
        $null = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
            'exec', $postgres.Name, 'rm', '-f', $remotePath
        )
    }

    if (-not (Test-Path -LiteralPath $destination)) {
        throw ('Backup file was not created: {0}' -f $destination)
    }

    $size = (Get-Item -LiteralPath $destination).Length
    if ($size -le 0) {
        throw ('Backup file is empty: {0}' -f $destination)
    }

    Write-BayiosLog ('Backup created: {0} ({1:N2} MiB)' -f $destination, ($size / 1MB)) 'OK'

    if (-not [string]::IsNullOrWhiteSpace($ExternalBackupDir)) {
        if (-not (Test-Path -LiteralPath $ExternalBackupDir)) {
            New-Item -ItemType Directory -Path $ExternalBackupDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $destination -Destination (Join-Path $ExternalBackupDir $fileName) -Force
        Write-BayiosLog ('External copy: {0}' -f (Join-Path $ExternalBackupDir $fileName)) 'OK'
    }

    $today = Get-Date
    $monday = $today.Date.AddDays(-(([int]$today.DayOfWeek + 6) % 7))
    $weekFile = 'bayios_week_{0}.dump' -f $monday.ToString('yyyyMMdd')
    $weekDestination = Join-Path $weekly $weekFile
    if (-not (Test-Path -LiteralPath $weekDestination)) {
        Copy-Item -LiteralPath $destination -Destination $weekDestination -Force
        Write-BayiosLog ('Weekly copy: {0}' -f $weekDestination) 'OK'
    }

    $monthFile = 'bayios_month_{0}.dump' -f $today.ToString('yyyy-MM')
    $monthDestination = Join-Path $monthly $monthFile
    if (-not (Test-Path -LiteralPath $monthDestination)) {
        Copy-Item -LiteralPath $destination -Destination $monthDestination -Force
        Write-BayiosLog ('Monthly copy: {0}' -f $monthDestination) 'OK'
    }

    # Retention removes old backup files only. It never removes containers,
    # volumes, databases, or the live data.
    $deleted = 0
    foreach ($item in @(Get-ChildItem -LiteralPath $daily -Filter 'bayios_*.dump' -File)) {
        if ($item.LastWriteTime -lt $today.AddDays(-$RetentionDaily)) {
            Remove-Item -LiteralPath $item.FullName -Force
            $deleted++
        }
    }
    foreach ($item in @(Get-ChildItem -LiteralPath $weekly -Filter 'bayios_*.dump' -File)) {
        if ($item.LastWriteTime -lt $today.AddDays(-($RetentionWeekly * 7))) {
            Remove-Item -LiteralPath $item.FullName -Force
            $deleted++
        }
    }
    foreach ($item in @(Get-ChildItem -LiteralPath $monthly -Filter 'bayios_*.dump' -File)) {
        if ($item.LastWriteTime -lt $today.AddDays(-($RetentionMonthly * 30))) {
            Remove-Item -LiteralPath $item.FullName -Force
            $deleted++
        }
    }

    return [pscustomobject]@{
        DailyPath       = $destination
        SizeBytes       = $size
        WeeklyPath      = $weekDestination
        MonthlyPath     = $monthDestination
        DeletedOldFiles = $deleted
    }
}

Export-ModuleMember -Function Write-BayiosLog, Set-BayiosLogFile, Start-BayiosLog,
    Get-BayiosRepoRoot, Get-BayiosDotEnvValue, Test-BayiosCommand, Invoke-BayiosCapture,
    Assert-BayiosPrerequisites, Start-BayiosPodmanMachine, Invoke-BayiosCompose,
    Invoke-BayiosComposeCapture, Get-BayiosProjectContainers, Get-BayiosServiceContainer,
    Stop-BayiosForeignContainers, Get-BayiosImageId, Get-BayiosContainerImageId,
    Get-BayiosHealth, Wait-BayiosHealth, Get-BayiosPort, Wait-BayiosPostgres,
    New-BayiosLock, Remove-BayiosLock, Get-BayiosGitInfo, Invoke-BayiosGitPull,
    Get-BayiosDiskFreeGB, Protect-BayiosSecrets, Invoke-BayiosBackup
