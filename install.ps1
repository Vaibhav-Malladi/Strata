param(
    [switch]$VerboseInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:InstallLogPath = Join-Path $script:RepoRoot ".aidc\install.log"
$script:RequiredPythonVersion = $null
$script:VerboseInstall = [bool]$VerboseInstall
$script:CheckMark = [char]0x2713

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
    Invoke-LoggedNativeCommand -Label "winget install" -FilePath "winget" -ArgumentList @("install", "--id", $packageId, "-e") -WorkingDirectory $script:RepoRoot | Out-Null
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

function Initialize-InstallLog {
    New-Item -ItemType Directory -Force -Path (Split-Path $script:InstallLogPath) | Out-Null
    if (-not (Test-Path $script:InstallLogPath)) {
        Set-Content -Path $script:InstallLogPath -Encoding utf8 -Value @(
            "Strata install log"
            ("Repository: {0}" -f $script:RepoRoot)
            ("Timestamp: {0}" -f (Get-Date))
            ""
        )
        return
    }

    Add-Content -Path $script:InstallLogPath -Encoding utf8 -Value @(
        ""
        ("=== New run: {0} ===" -f (Get-Date))
        ""
    )
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

function Invoke-LoggedNativeCommand {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory = $script:RepoRoot
    )

    $stdout = [System.IO.Path]::GetTempFileName()
    $stderr = [System.IO.Path]::GetTempFileName()

    try {
        Add-Content -Path $script:InstallLogPath -Encoding utf8 -Value @(
            ("=== {0} ===" -f $Label)
            ("Command: {0}" -f (Format-CommandLine -FilePath $FilePath -ArgumentList $ArgumentList))
            ("Working directory: {0}" -f $WorkingDirectory)
            ""
        )

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
            Add-Content -Path $script:InstallLogPath -Encoding utf8 -Value $stdoutText
        }

        if ($stderrText) {
            Add-Content -Path $script:InstallLogPath -Encoding utf8 -Value $stderrText
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

function Show-Failure {
    param(
        [string]$Message
    )

    Write-Host $Message
    Write-Host "Detailed logs:"
    Write-Host ("  {0}" -f $script:InstallLogPath)
}

$script:RequiredPythonVersion = Get-RequiredPythonVersion
Initialize-InstallLog

Write-Host "========================================"
Write-Host " Strata Installer"
Write-Host "========================================"
Write-Host ""
Write-Host ("Repository: {0}" -f $script:RepoRoot)
Write-Host ("Required Python: {0}.{1}+" -f $script:RequiredPythonVersion.Major, $script:RequiredPythonVersion.Minor)
Write-Host ""

if (-not (Test-PyLauncher)) {
    Show-Failure "Python launcher `py` was not found."
    Write-Host "Install Python manually, then reopen this terminal and run install.ps1 again."
    exit 1
}

$pythonVersion = Get-PythonVersion
if (-not $pythonVersion) {
    if (Test-Winget) {
        if (Confirm-Yes "Install Python using winget now? [y/N]") {
            $wingetResult = Invoke-LoggedNativeCommand -Label "winget install Python" -FilePath "winget" -ArgumentList @("install", "--id", "Python.Python.3.13", "-e")
            if ($wingetResult.ExitCode -ne 0) {
                Show-Failure "Python installation failed."
                Write-Host "Run `install.ps1 -VerboseInstall` to see the full output."
                exit 1
            }

            $pythonVersion = Get-PythonVersion
            if (-not $pythonVersion) {
                Show-Failure "Python still was not detected after winget finished."
                Write-Host "Restart your terminal, then run install.ps1 again."
                exit 1
            }
        } else {
            Show-Failure "Python is required before Strata can be installed."
            exit 1
        }
    } else {
        Show-Failure "winget is not available, so Strata cannot bootstrap Python automatically."
        Write-Host ("Install Python {0}.{1}+ manually, then rerun install.ps1." -f $script:RequiredPythonVersion.Major, $script:RequiredPythonVersion.Minor)
        exit 1
    }
}

if (-not (Test-PythonMeetsRequirement -Version $pythonVersion -Required $script:RequiredPythonVersion)) {
    Write-Host ("Detected Python {0}.{1}, but Strata requires {2}.{3}+." -f $pythonVersion.Major, $pythonVersion.Minor, $script:RequiredPythonVersion.Major, $script:RequiredPythonVersion.Minor)
    if (Test-Winget) {
        if (Confirm-Yes "Install Python using winget now? [y/N]") {
            $wingetResult = Invoke-LoggedNativeCommand -Label "winget install Python" -FilePath "winget" -ArgumentList @("install", "--id", "Python.Python.3.13", "-e")
            if ($wingetResult.ExitCode -ne 0) {
                Show-Failure "Python installation failed."
                Write-Host "Run `install.ps1 -VerboseInstall` to see the full output."
                exit 1
            }

            $pythonVersion = Get-PythonVersion
            if (-not $pythonVersion) {
                Show-Failure "Python still was not detected after winget finished."
                Write-Host "Restart your terminal, then run install.ps1 again."
                exit 1
            }

            if (-not (Test-PythonMeetsRequirement -Version $pythonVersion -Required $script:RequiredPythonVersion)) {
                Show-Failure "The installed Python version is still too old."
                Write-Host "Restart your terminal after updating Python, then rerun install.ps1."
                exit 1
            }
        } else {
            Show-Failure ("Strata needs Python {0}.{1}+." -f $script:RequiredPythonVersion.Major, $script:RequiredPythonVersion.Minor)
            exit 1
        }
    } else {
        Show-Failure "winget is not available, so Strata cannot bootstrap Python automatically."
        Write-Host ("Install Python {0}.{1}+ manually, then rerun install.ps1." -f $script:RequiredPythonVersion.Major, $script:RequiredPythonVersion.Minor)
        exit 1
    }
}

Write-Host ""
Write-Host ("{0} Python found: {1}.{2}" -f $script:CheckMark, $pythonVersion.Major, $pythonVersion.Minor)
Write-Host "Running editable install quietly..."

$pipResult = Invoke-LoggedNativeCommand -Label "pip install -e" -FilePath "py" -ArgumentList @("-m", "pip", "install", "-e", $script:RepoRoot)
if ($pipResult.ExitCode -ne 0) {
    Show-Failure "Editable install failed."
    Write-Host "Run `install.ps1 -VerboseInstall` to see the full output."
    exit 1
}

Write-Host ("{0} Strata installed" -f $script:CheckMark)

$strataCommand = Get-Command strata -ErrorAction SilentlyContinue
if (-not $strataCommand) {
    Show-Failure "The `strata` command is not on PATH after installation."
    Write-Host "Restart VS Code or your terminal after PATH changes, then rerun install.ps1."
    exit 1
}

Write-Host ("{0} strata command found" -f $script:CheckMark)

$helpResult = Invoke-LoggedNativeCommand -Label "strata help" -FilePath "strata" -ArgumentList @("help")
if ($helpResult.ExitCode -ne 0) {
    Show-Failure "strata help failed."
    Write-Host "Run `install.ps1 -VerboseInstall` to see the full output."
    exit 1
}

Write-Host ("{0} strata command available" -f $script:CheckMark)

$diagnosticResult = Invoke-LoggedNativeCommand -Label "strata doctor install" -FilePath "strata" -ArgumentList @("doctor", "install")

if ($diagnosticResult.ExitCode -ne 0) {
    Show-Failure "Install diagnostics failed."
    Write-Host "Run `install.ps1 -VerboseInstall` to see the full output."
    exit 1
}

Write-Host ("{0} install diagnostics passed" -f $script:CheckMark)
Write-Host ""
Write-Host "Next:"
Write-Host "  strata start"
Write-Host ""
Write-Host "Detailed logs:"
Write-Host ("  {0}" -f $script:InstallLogPath)
