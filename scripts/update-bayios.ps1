#requires -Version 5.1
# Builds and deploys the current checkout, applies forward Alembic migrations,
# recreates only the app container, and verifies health + image identity.
# It never runs "down -v", never removes volumes, and never restores a database.

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$ProjectName = 'bayios',
    [string]$ComposeFile = '',
    [string]$Branch = '',
    [int]$Port = 0,
    [int]$TimeoutSeconds = 300,
    [switch]$SkipPull,
    [switch]$SkipBackup,
    [string]$BackupDir = '',
    [string]$ExternalBackupDir = '',
    [bool]$RollbackOnFailure = $true,
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

function Get-BayiosAllembicHead {
    param([string]$ComposeFilePath)

    $result = Invoke-BayiosComposeCapture -ComposeFile $ComposeFilePath -Arguments @(
        'run', '--rm', 'app', 'alembic', 'current'
    )
    if ($result.ExitCode -ne 0) {
        return 'unknown'
    }

    $heads = @($result.Output -split "`r?`n" | Where-Object { $_ -match '^\s*\d{4}' })
    if ($heads.Count -gt 0) {
        return $heads[-1].Trim()
    }
    return 'unknown'
}

$null = Start-BayiosLog -RepoPath $root -Action 'update'
$lock = $null
$oldImageId = $null
$newImageId = $null
$recreated = $false
$headBefore = 'unknown'
$headAfter = 'unknown'
$backupPath = ''

try {
    $lock = New-BayiosLock -RepoPath $root

    if (-not $NoMachine) {
        Start-BayiosPodmanMachine -TimeoutSeconds $TimeoutSeconds
    }

    Assert-BayiosPrerequisites -RepoPath $root -ComposeFile $ComposeFile -RequireGit

    $gitInfo = Get-BayiosGitInfo -RepoPath $root
    Write-BayiosLog ('Current checkout: branch={0} commit={1}' -f $gitInfo.Branch, $gitInfo.Commit)

    if (-not $SkipPull) {
        Invoke-BayiosGitPull -RepoPath $root -Branch $Branch
        $gitInfo = Get-BayiosGitInfo -RepoPath $root
        Write-BayiosLog ('Updated checkout: branch={0} commit={1}' -f $gitInfo.Branch, $gitInfo.Commit)
    } else {
        Write-BayiosLog 'Skipping git pull because -SkipPull was supplied.' 'WARN'
    }

    Stop-BayiosForeignContainers -ProjectName $ProjectName

    $oldImageId = Get-BayiosImageId -Image 'localhost/bayios:latest'
    if ($oldImageId) {
        $tagPrevious = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
            'tag', 'localhost/bayios:latest', 'localhost/bayios:previous'
        )
        if ($tagPrevious.ExitCode -ne 0) {
            Write-BayiosLog ('Could not tag the previous image: {0}' -f $tagPrevious.Output) 'WARN'
        } else {
            Write-BayiosLog ('Previous image saved as localhost/bayios:previous ({0})' -f $oldImageId)
        }
    } else {
        Write-BayiosLog 'No previous localhost/bayios:latest image found; first deploy.' 'WARN'
    }

    $headBefore = Get-BayiosAllembicHead -ComposeFilePath $ComposeFile
    Write-BayiosLog ('Alembic head before update: {0}' -f $headBefore)

    $env:GIT_SHA = $gitInfo.Commit
    $env:BUILD_TIME = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')

    Write-BayiosLog ('Building image with GIT_SHA={0} BUILD_TIME={1}' -f $env:GIT_SHA, $env:BUILD_TIME)
    Invoke-BayiosCompose -ComposeFile $ComposeFile -Arguments @('build', 'app') | Out-Null

    $newImageId = Get-BayiosImageId -Image 'localhost/bayios:latest'
    if (-not $newImageId) {
        throw 'Build finished but localhost/bayios:latest is still missing.'
    }
    Write-BayiosLog ('New image: {0}' -f $newImageId) 'OK'

    $versionTag = 'localhost/bayios:{0}' -f $gitInfo.Commit
    $tagVersion = Invoke-BayiosCapture -FilePath 'podman' -Arguments @('tag', 'localhost/bayios:latest', $versionTag)
    if ($tagVersion.ExitCode -ne 0) {
        Write-BayiosLog ('Could not create version tag {0}: {1}' -f $versionTag, $tagVersion.Output) 'WARN'
    }

    if (-not $SkipBackup) {
        $backup = Invoke-BayiosBackup -RepoPath $root -ComposeFile $ComposeFile -ProjectName $ProjectName -BackupDir $BackupDir -ExternalBackupDir $ExternalBackupDir
        $backupPath = $backup.DailyPath
        Write-BayiosLog ('Pre-migration backup: {0}' -f $backupPath) 'OK'
    } else {
        Write-BayiosLog 'Skipping pre-migration backup because -SkipBackup was supplied.' 'WARN'
    }

    Invoke-BayiosCompose -ComposeFile $ComposeFile -Arguments @('up', '-d', 'postgres') | Out-Null
    $null = Wait-BayiosPostgres -ProjectName $ProjectName

    Write-BayiosLog 'Applying Alembic migrations ...'
    Invoke-BayiosCompose -ComposeFile $ComposeFile -Arguments @(
        'run', '--rm', 'app', 'alembic', 'upgrade', 'head'
    ) | Out-Null

    $headAfter = Get-BayiosAllembicHead -ComposeFilePath $ComposeFile
    Write-BayiosLog ('Alembic head after update: {0}' -f $headAfter)

    Write-BayiosLog 'Recreating the app container with the new image ...'
    $recreated = $true
    Invoke-BayiosCompose -ComposeFile $ComposeFile -Arguments @(
        'up', '-d', '--force-recreate', '--no-deps', 'app'
    ) | Out-Null

    $app = Get-BayiosServiceContainer -ProjectName $ProjectName -Service 'app'
    if (-not $app) {
        throw 'The app container was not created.'
    }

    $runningImageId = Get-BayiosContainerImageId -ContainerName $app.Name
    if ($runningImageId -ne $newImageId) {
        throw ('Running app image mismatch. container={0} expected={1}' -f $runningImageId, $newImageId)
    }
    Write-BayiosLog ('App container image verified: {0}' -f $runningImageId) 'OK'

    $health = Wait-BayiosHealth -Port $port -TimeoutSeconds $TimeoutSeconds
    $healthy = ($health -and $health.Json -and $health.Json.status -eq 'ok' -and
        $health.Json.migrations -and $health.Json.migrations.status -eq 'ok')

    if (-not $healthy) {
        $detail = 'health did not become ready'
        if ($health -and $health.Error) { $detail = $health.Error }
        elseif ($health -and $health.Body) { $detail = Protect-BayiosSecrets -Text $health.Body }
        throw ('New app did not become healthy on port {0}: {1}' -f $port, $detail)
    }

    $buildSha = 'unknown'
    if ($health.Json.build -and $health.Json.build.sha) { $buildSha = $health.Json.build.sha }

    if ($buildSha -ne 'unknown' -and $buildSha -ne $gitInfo.Commit) {
        Write-BayiosLog ('Health build.sha ({0}) differs from git commit ({1}). The running image ID was verified, but this usually means only docs/scripts changed and the cached source layer was reused.' -f $buildSha, $gitInfo.Commit) 'WARN'
    }

    Write-BayiosLog ('Update complete. commit={0} image={1} build_sha={2} port={3}' -f $gitInfo.Commit, $newImageId, $buildSha, $port) 'OK'
    if ($backupPath) {
        Write-BayiosLog ('Rollback backup: {0}' -f $backupPath)
    }
} catch {
    $message = $_.Exception.Message
    Write-BayiosLog $message 'ERROR'

    if ($RollbackOnFailure -and $oldImageId -and $recreated) {
        try {
            Write-BayiosLog 'Rolling back the app image to localhost/bayios:previous ...' 'WARN'
            $rollbackTag = Invoke-BayiosCapture -FilePath 'podman' -Arguments @(
                'tag', 'localhost/bayios:previous', 'localhost/bayios:latest'
            )
            if ($rollbackTag.ExitCode -ne 0) {
                throw ('Could not retag the previous image: {0}' -f $rollbackTag.Output)
            }

            Invoke-BayiosCompose -ComposeFile $ComposeFile -Arguments @(
                'up', '-d', '--force-recreate', '--no-deps', 'app'
            ) | Out-Null

            $deadline = (Get-Date).AddSeconds(120)
            $rollbackHealth = $null
            while ((Get-Date) -lt $deadline) {
                $rollbackHealth = Get-BayiosHealth -Port $port
                if ($rollbackHealth.Json -and $rollbackHealth.Json.database -eq 'ok') { break }
                Start-Sleep -Seconds 2
            }

            if ($rollbackHealth -and $rollbackHealth.Json -and $rollbackHealth.Json.database -eq 'ok') {
                Write-BayiosLog 'Previous image is reachable again.' 'OK'
            } else {
                Write-BayiosLog 'Previous image was retagged but the app did not become reachable.' 'ERROR'
            }

            if ($headAfter -ne $headBefore -and $headAfter -ne 'unknown' -and $headBefore -ne 'unknown') {
                Write-BayiosLog ('Database head changed ({0} -> {1}). Image rollback is not a full database rollback; restore the pre-update backup if needed.' -f $headBefore, $headAfter) 'ERROR'
            }
        } catch {
            Write-BayiosLog ('Rollback failed: {0}' -f $_.Exception.Message) 'ERROR'
        }
    } elseif ($recreated) {
        Write-BayiosLog 'Automatic image rollback is disabled or unavailable.' 'WARN'
    }

    Write-BayiosLog 'Update failed. The previous container was left running when possible.' 'ERROR'
    exit 1
} finally {
    Remove-BayiosLock -Lock $lock
}
