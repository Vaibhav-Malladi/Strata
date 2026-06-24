$ErrorActionPreference = "Stop"

Set-StrictMode -Version Latest

function Test-PyLauncher {
    return [bool](Get-Command py -ErrorAction SilentlyContinue)
}

function Test-Winget {
    return [bool](Get-Command winget -ErrorAction SilentlyContinue)
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

function Get-RequiredPythonVersion {
    $pyprojectPath = Join-Path $script:RepoRoot "pyproject.toml"
    if (Test-Path $pyprojectPath) {
        $content = Get-Content $pyprojectPath -Raw
        if ($content -match 'requires-python\s*=\s*">=([0-9]+)\.([0-9]+)"') {
            return [pscustomobject]@{
                Major = [int]$Matches[1]
                Minor = [int]$Matches[2]
            }
        }
    }

    return [pscustomobject]@{
        Major = 3
        Minor = 10
    }
}

function Get-PythonVersion {
    try {
        $output = & py -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
    } catch {
        return $null
    }

    if ($LASTEXITCODE -ne 0 -or -not $output) {
        return $null
    }

    $parts = $output.Trim().Split(".")
    if ($parts.Count -lt 2) {
        return $null
    }

    return [pscustomobject]@{
        Major = [int]$parts[0]
        Minor = [int]$parts[1]
    }
}

function Test-PythonMeetsRequirement {
    param(
        [pscustomobject]$Version,
        [pscustomobject]$Required
    )

    if (-not $Version -or -not $Required) {
        return $false
    }

    if ($Version.Major -gt $Required.Major) {
        return $true
    }

    if ($Version.Major -lt $Required.Major) {
        return $false
    }

    return $Version.Minor -ge $Required.Minor
}

function Install-PythonWithWinget {
    $packageId = "Python.Python.3.13"
    Write-Host ("Installing Python with winget: {0}" -f $packageId)
    & winget install --id $packageId -e
}

function Get-PythonScriptsDir {
    try {
        $scriptsDir = & py -c "import sysconfig; print(sysconfig.get_path('scripts'))" 2>$null
    } catch {
        return $null
    }

    if ($LASTEXITCODE -ne 0 -or -not $scriptsDir) {
        return $null
    }

    return $scriptsDir.Trim()
}

function Add-UserPathEntry {
    param(
        [string]$Entry
    )

    if (-not $Entry) {
        return
    }

    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if ($current) {
        $parts = $current.Split(";") | Where-Object { $_ -and $_.Trim() }
    }

    if ($parts -contains $Entry) {
        return
    }

    $updated = @($parts + $Entry) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $updated, "User")
}

$script:RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:RequiredPythonVersion = Get-RequiredPythonVersion

Write-Host "========================================"
Write-Host " Strata Installer"
Write-Host "========================================"
Write-Host ""
Write-Host ("Repository: {0}" -f $script:RepoRoot)
Write-Host ("Required Python: {0}.{1}+" -f $script:RequiredPythonVersion.Major, $script:RequiredPythonVersion.Minor)
Write-Host ""

if (-not (Test-PyLauncher)) {
    Write-Host "Python launcher `py` was not found."
    Write-Host "Install Python manually, then reopen this terminal and run install.ps1 again."
    exit 1
}

$pythonVersion = Get-PythonVersion
if (-not $pythonVersion) {
    Write-Host "Python could not be detected through `py`."
    if (Test-Winget) {
        if (Confirm-Yes "Install Python using winget now? [y/N]") {
            Install-PythonWithWinget
            $pythonVersion = Get-PythonVersion
            if (-not $pythonVersion) {
                Write-Host "Python still was not detected after winget finished."
                Write-Host "Restart your terminal, then run install.ps1 again."
                exit 1
            }
        } else {
            Write-Host "Python is required before Strata can be installed."
            exit 1
        }
    } else {
        Write-Host "winget is not available, so Strata cannot bootstrap Python automatically."
        Write-Host "Install Python manually, then rerun install.ps1."
        exit 1
    }
}

if (-not (Test-PythonMeetsRequirement -Version $pythonVersion -Required $script:RequiredPythonVersion)) {
    Write-Host ("Detected Python {0}.{1}, but Strata requires {2}.{3}+." -f $pythonVersion.Major, $pythonVersion.Minor, $script:RequiredPythonVersion.Major, $script:RequiredPythonVersion.Minor)
    if (Test-Winget) {
        if (Confirm-Yes "Install Python using winget now? [y/N]") {
            Install-PythonWithWinget
            $pythonVersion = Get-PythonVersion
            if (-not $pythonVersion) {
                Write-Host "Python still was not detected after winget finished."
                Write-Host "Restart your terminal, then run install.ps1 again."
                exit 1
            }
            if (-not (Test-PythonMeetsRequirement -Version $pythonVersion -Required $script:RequiredPythonVersion)) {
                Write-Host "The installed Python version is still too old."
                Write-Host "Restart your terminal after updating Python, then rerun install.ps1."
                exit 1
            }
        } else {
            Write-Host ("Strata needs Python {0}.{1}+." -f $script:RequiredPythonVersion.Major, $script:RequiredPythonVersion.Minor)
            exit 1
        }
    } else {
        Write-Host "winget is not available, so Strata cannot bootstrap Python automatically."
        Write-Host ("Install Python {0}.{1}+ manually, then rerun install.ps1." -f $script:RequiredPythonVersion.Major, $script:RequiredPythonVersion.Minor)
        exit 1
    }
}

Write-Host ""
Write-Host "Installing Strata in editable mode..."
& py -m pip install -e $script:RepoRoot
if ($LASTEXITCODE -ne 0) {
    Write-Host "Editable install failed."
    Write-Host "Run `py -m pip install -e .` manually from the repo root for details."
    exit 1
}

Write-Host ""
Write-Host "Checking whether `strata` is on PATH..."
$strataCommand = Get-Command strata -ErrorAction SilentlyContinue
if (-not $strataCommand) {
    $scriptsDir = Get-PythonScriptsDir
    Write-Host "The install succeeded, but `strata` is not currently on PATH."
    if ($scriptsDir) {
        Write-Host ("Likely Scripts folder: {0}" -f $scriptsDir)
        if (Confirm-Yes "Add the Python Scripts folder to your user PATH? [y/N]") {
            Add-UserPathEntry -Entry $scriptsDir
            Write-Host "User PATH updated."
            Write-Host "Restart VS Code and any open terminals so PATH changes take effect."
        } else {
            Write-Host "PATH was left unchanged."
            Write-Host "Restart VS Code or your terminal after fixing PATH manually."
        }
    } else {
        Write-Host "Could not detect a Python Scripts folder automatically."
        Write-Host "Restart VS Code or your terminal after fixing PATH manually."
    }
} else {
    Write-Host ("Resolved strata command: {0}" -f $strataCommand.Source)
}

Write-Host ""
Write-Host "Running install diagnostics..."
& py -m strata doctor install
if ($LASTEXITCODE -ne 0) {
    Write-Host "Install diagnostics reported a problem, but the install completed."
}

Write-Host ""
Write-Host "Try: strata start"
