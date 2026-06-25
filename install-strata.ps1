param(
    [string]$RepoUrl = "https://github.com/Vaibhav-Malladi/Strata.git",
    [string]$InstallDir = (Join-Path $env:USERPROFILE "Strata"),
    [string]$Branch = "main",
    [switch]$VerboseInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:VerboseInstall = [bool]$VerboseInstall
$script:CheckMark = [char]0x2713
$script:BootstrapLogPath = [System.IO.Path]::GetTempFileName()
$script:InstallLogPath = Join-Path $InstallDir ".aidc\install.log"

function Test-CommandAvailable {
    param(
        [string]$Name
    )

    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Confirm-Yes {
    param(
        [string]$Prompt
    )

    $response = Read-Host $Prompt
    if ($null -eq $response) {
        $response = ""
    }

    $normalized = $response.Trim().ToLowerInvariant()
    return $normalized -eq "y" -or $normalized -eq "yes"
}

function Confirm-YesDefaultYes {
    param(
        [string]$Prompt
    )

    $response = Read-Host $Prompt
    if ($null -eq $response) {
        return $true
    }

    if ([string]::IsNullOrWhiteSpace($response)) {
        return $true
    }

    $normalized = $response.Trim().ToLowerInvariant()
    return $normalized -eq "y" -or $normalized -eq "yes"
}

function Test-GitRepository {
    param(
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return $false
    }

    try {
        & git -C $Path rev-parse --is-inside-work-tree *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-GitStatusShort {
    param(
        [string]$Path
    )

    try {
        $status = & git -C $Path status --short 2>$null
    } catch {
        return $null
    }

    if ($LASTEXITCODE -ne 0) {
        return $null
    }

    return $status
}

function Format-CommandLine {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    $parts = @($FilePath)
    foreach ($argument in $ArgumentList) {
        if ($argument -match '\s') {
            $parts += ('"{0}"' -f $argument)
        } else {
            $parts += $argument
        }
    }

    return $parts -join " "
}

function Initialize-BootstrapLog {
    New-Item -ItemType Directory -Force -Path (Split-Path $script:BootstrapLogPath) | Out-Null
    Set-Content -Path $script:BootstrapLogPath -Encoding utf8 -Value @(
        "Strata bootstrap install log"
        ("Repository URL: {0}" -f $RepoUrl)
        ("Install directory: {0}" -f $InstallDir)
        ("Branch: {0}" -f $Branch)
        ("Timestamp: {0}" -f (Get-Date))
        ""
    )
}

function Add-BootstrapLog {
    param(
        [string]$Text
    )

    if (-not $Text) {
        return
    }

    Add-Content -Path $script:BootstrapLogPath -Encoding utf8 -Value $Text
}

function Invoke-LoggedNativeCommand {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory = $env:TEMP
    )

    $stdout = [System.IO.Path]::GetTempFileName()
    $stderr = [System.IO.Path]::GetTempFileName()

    try {
        Add-BootstrapLog ("=== {0} ===" -f $Label)
        Add-BootstrapLog ("Command: {0}" -f (Format-CommandLine -FilePath $FilePath -ArgumentList $ArgumentList))
        Add-BootstrapLog ("Working directory: {0}" -f $WorkingDirectory)
        Add-BootstrapLog ""

        $process = Start-Process `
            -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr

        $stdoutText = if (Test-Path $stdout) { Get-Content $stdout -Raw } else { "" }
        $stderrText = if (Test-Path $stderr) { Get-Content $stderr -Raw } else { "" }

        if ($stdoutText) {
            Add-BootstrapLog $stdoutText
        }

        if ($stderrText) {
            Add-BootstrapLog $stderrText
        }

        if ($script:VerboseInstall) {
            if ($stdoutText) {
                Write-Host $stdoutText -NoNewline
            }

            if ($stderrText) {
                Write-Host $stderrText -NoNewline
            }
        }

        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Stdout = $stdoutText
            Stderr = $stderrText
        }
    } finally {
        Remove-Item -Force $stdout, $stderr -ErrorAction SilentlyContinue
    }
}

function Merge-BootstrapLogIntoInstallLog {
    if (-not (Test-Path $script:InstallLogPath)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $script:InstallLogPath) | Out-Null
        Set-Content -Path $script:InstallLogPath -Encoding utf8 -Value @(
            "Strata install log"
            ("Repository: {0}" -f $InstallDir)
            ("Timestamp: {0}" -f (Get-Date))
            ""
        )
    }

    if (Test-Path $script:BootstrapLogPath) {
        $bootstrapContent = Get-Content $script:BootstrapLogPath -Raw
        if ($bootstrapContent) {
            Add-Content -Path $script:InstallLogPath -Encoding utf8 -Value @(
                ""
                "=== Bootstrap ==="
                ""
            )
            Add-Content -Path $script:InstallLogPath -Encoding utf8 -Value $bootstrapContent
        }
    }
}

function Show-Failure {
    param(
        [string]$Message,
        [string]$LogPath
    )

    Write-Host $Message
    Write-Host "Detailed logs:"
    Write-Host ("  {0}" -f $LogPath)
}

function Invoke-InnerInstaller {
    param(
        [string]$RepoPath
    )

    $installerPath = Join-Path $RepoPath "install.ps1"
    if (-not (Test-Path $installerPath)) {
        Show-Failure "Repo-local install.ps1 was not found." $script:InstallLogPath
        Write-Host "The checkout may be incomplete."
        exit 1
    }

    Write-Host ""
    Write-Host "Running repo-local installer..."

    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $installerPath)
    if ($script:VerboseInstall) {
        $arguments += "-VerboseInstall"
    }

    & powershell @arguments
    if ($LASTEXITCODE -ne 0) {
        Show-Failure "Repo-local installer did not complete successfully." $script:InstallLogPath
        exit 1
    }
}

Write-Host "========================================"
Write-Host " Strata Bootstrap Installer"
Write-Host "========================================"
Write-Host ""
Write-Host ("Repo URL: {0}" -f $RepoUrl)
Write-Host ("Install directory: {0}" -f $InstallDir)
Write-Host ("Branch: {0}" -f $Branch)
Write-Host ""
Write-Host "This bootstrap installer will:"
Write-Host "  - install or update Strata at the install directory"
Write-Host "  - check Git first"
Write-Host "  - run the repo-local install.ps1"
Write-Host "  - let install.ps1 handle Python and PATH prompts"
Write-Host '  - verify `strata doctor install` quietly'
Write-Host '  - verify `strata help` quietly'
Write-Host ""

if (-not (Test-CommandAvailable git)) {
    if (Test-CommandAvailable winget) {
        if (Confirm-Yes "Install Git using winget now? [y/N]") {
            $wingetResult = Invoke-LoggedNativeCommand -Label "winget install Git" -FilePath "winget" -ArgumentList @("install", "--id", "Git.Git", "-e") -WorkingDirectory $env:TEMP
            if ($wingetResult.ExitCode -ne 0) {
                Show-Failure "Git installation failed." $script:BootstrapLogPath
                exit 1
            }

            if (-not (Test-CommandAvailable git)) {
                Show-Failure "Git is still not available after winget finished." $script:BootstrapLogPath
                Write-Host "Restart your terminal, then rerun install-strata.ps1."
                exit 1
            }
        } else {
            Show-Failure "Git is required before Strata can be installed." $script:BootstrapLogPath
            exit 1
        }
    } else {
        Show-Failure "Git is not installed, and winget is unavailable." $script:BootstrapLogPath
        Write-Host "Install Git manually, then rerun install-strata.ps1."
        exit 1
    }
}

Initialize-BootstrapLog

if (Test-Path $InstallDir) {
    if (-not (Test-GitRepository $InstallDir)) {
        Show-Failure "The install directory already exists, but it is not a git repository." $script:BootstrapLogPath
        Write-Host "Choose a different InstallDir or move this folder aside before rerunning."
        exit 1
    }

    $status = Get-GitStatusShort $InstallDir
    if ($status) {
        Show-Failure "Local changes exist in the existing Strata checkout:" $script:BootstrapLogPath
        Write-Host $status
        Write-Host "Resolve, commit, or stash those changes manually, then rerun install-strata.ps1."
        exit 1
    }

    if (-not (Confirm-YesDefaultYes "Update existing Strata checkout? [Y/n]")) {
        Write-Host "Existing checkout left unchanged."
        exit 0
    }

    Write-Host "Updating existing Strata checkout..."
    $gitResult = Invoke-LoggedNativeCommand -Label "git pull --ff-only" -FilePath "git" -ArgumentList @("-C", $InstallDir, "pull", "--ff-only") -WorkingDirectory $InstallDir
    if ($gitResult.ExitCode -ne 0) {
        Show-Failure "Git update failed." $script:BootstrapLogPath
        exit 1
    }
} else {
    Write-Host "Cloning Strata..."
    $gitResult = Invoke-LoggedNativeCommand -Label "git clone" -FilePath "git" -ArgumentList @("clone", "--branch", $Branch, $RepoUrl, $InstallDir) -WorkingDirectory $env:TEMP
    if ($gitResult.ExitCode -ne 0) {
        Show-Failure "Git clone failed." $script:BootstrapLogPath
        exit 1
    }
}

Merge-BootstrapLogIntoInstallLog
Write-Host ("{0} Strata checkout ready" -f $script:CheckMark)

Invoke-InnerInstaller -RepoPath $InstallDir
