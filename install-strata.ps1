param(
    [string]$RepoUrl = "https://github.com/Vaibhav-Malladi/Strata.git",
    [string]$InstallDir = (Join-Path $env:USERPROFILE "Strata"),
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

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

function Install-GitWithWinget {
    Write-Host "Installing Git with winget..."
    & winget install --id Git.Git -e
}

function Invoke-InnerInstaller {
    param(
        [string]$RepoPath
    )

    $installerPath = Join-Path $RepoPath "install.ps1"
    if (-not (Test-Path $installerPath)) {
        Write-Host "Repo-local install.ps1 was not found."
        Write-Host "The checkout may be incomplete."
        exit 1
    }

    Write-Host ""
    Write-Host "Running repo-local installer..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installerPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Repo-local installer did not complete successfully."
        exit 1
    }
}

function Invoke-Verification {
    param(
        [string]$RepoPath
    )

    Write-Host ""
    Write-Host "Verifying installation..."
    & py -m strata help
    if ($LASTEXITCODE -ne 0) {
        Write-Host "py -m strata help failed."
    }

    $strataCommand = Get-Command strata -ErrorAction SilentlyContinue
    if ($strataCommand) {
        Write-Host ""
        Write-Host "Running strata doctor install..."
        & strata doctor install
        if ($LASTEXITCODE -ne 0) {
            Write-Host "strata doctor install reported a problem."
        }
        return
    }

    Write-Host ""
    Write-Host "strata is not on PATH yet."
    Write-Host "Running fallback verification with py -m strata doctor install..."
    & py -m strata doctor install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Fallback verification reported a problem."
    } else {
        Write-Host "py -m strata works. Restart VS Code or your terminal after PATH changes."
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
Write-Host '  - verify `strata doctor install`'
Write-Host '  - verify `py -m strata help`'
Write-Host ""

if (-not (Test-CommandAvailable git)) {
    if (Test-CommandAvailable winget) {
        if (Confirm-Yes "Install Git using winget now? [y/N]") {
            Install-GitWithWinget
            if (-not (Test-CommandAvailable git)) {
                Write-Host "Git is still not available after winget finished."
                Write-Host "Restart your terminal, then rerun install-strata.ps1."
                exit 1
            }
        } else {
            Write-Host "Git is required before Strata can be installed."
            exit 1
        }
    } else {
        Write-Host "Git is not installed, and winget is unavailable."
        Write-Host "Install Git manually, then rerun install-strata.ps1."
        exit 1
    }
}

if (Test-Path $InstallDir) {
    if (-not (Test-GitRepository $InstallDir)) {
        Write-Host "The install directory already exists, but it is not a git repository."
        Write-Host "Choose a different InstallDir or move this folder aside before rerunning."
        exit 1
    }

    $status = Get-GitStatusShort $InstallDir
    if ($status) {
        Write-Host "Local changes exist in the existing Strata checkout:"
        Write-Host $status
        Write-Host "Resolve, commit, or stash those changes manually, then rerun install-strata.ps1."
        exit 1
    }

    if (-not (Confirm-YesDefaultYes "Update existing Strata checkout? [Y/n]")) {
        Write-Host "Existing checkout left unchanged."
        exit 0
    }

    Write-Host ""
    Write-Host "Updating existing Strata checkout..."
    & git -C $InstallDir pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Git update failed."
        exit 1
    }
} else {
    Write-Host "Cloning Strata..."
    & git clone --branch $Branch $RepoUrl $InstallDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Git clone failed."
        exit 1
    }
}

Invoke-InnerInstaller -RepoPath $InstallDir
Invoke-Verification -RepoPath $InstallDir

Write-Host ""
Write-Host "Try:"
Write-Host "  strata start"
