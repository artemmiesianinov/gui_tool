# Sets up a Windows build environment for the DroneCAN GUI Tool and builds the MSI installer.
#
# Requirements: Windows 10/11 with winget (App Installer), and a git checkout of gui_tool.
#
# Usage, from a PowerShell prompt in the gui_tool directory:
#   powershell -ExecutionPolicy Bypass -File .\winbuild_env.ps1             # set up the environment and build the MSI
#   powershell -ExecutionPolicy Bypass -File .\winbuild_env.ps1 -SetupOnly  # only set up the environment
#   powershell -ExecutionPolicy Bypass -File .\winbuild_env.ps1 -Clean      # recreate the environment from scratch
#   powershell -ExecutionPolicy Bypass -File .\winbuild_env.ps1 -BasePython C:\Python310\python.exe
#                                                     # use this interpreter instead of finding or installing one (CI)
#
# The MSI is written to the 'dist' folder.
# Python 3.14 matches the CI build (.github/workflows/winbuild.yml). Keep the two in step.

param(
    [switch]$SetupOnly,
    [switch]$Clean,
    [string]$BasePython
)

$ErrorActionPreference = 'Stop'

$PythonVersion = '3.14'
$VenvDir = Join-Path $PSScriptRoot '.venv-win'
$Python = Join-Path $VenvDir 'Scripts\python.exe'

# Native commands don't throw on failure, so check their exit codes explicitly
function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    Write-Host ">> $Exe $($Arguments -join ' ')" -ForegroundColor Cyan
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Exe $($Arguments -join ' ')"
    }
}

function Test-PythonInstalled {
    try {
        & py "-$PythonVersion" --version *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

Set-Location $PSScriptRoot

# Python
if ($BasePython) {
    Invoke-Checked $BasePython @('--version')
} elseif (-not (Test-PythonInstalled)) {
    Write-Host "Python $PythonVersion not found, installing it with winget" -ForegroundColor Yellow
    Invoke-Checked 'winget' @('install', '--id', "Python.Python.$PythonVersion", '-e',
                              '--accept-package-agreements', '--accept-source-agreements')
    # winget installs the 'py' launcher, but the current session doesn't see the updated PATH
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not (Test-PythonInstalled)) {
        throw "Python $PythonVersion is still not available; open a new PowerShell window and run the script again"
    }
}

# Virtual environment
if ($Clean -and (Test-Path $VenvDir)) {
    Write-Host "Removing $VenvDir" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $VenvDir
}
if (-not (Test-Path $Python)) {
    if ($BasePython) {
        Invoke-Checked $BasePython @('-m', 'venv', $VenvDir)
    } else {
        Invoke-Checked 'py' @("-$PythonVersion", '-m', 'venv', $VenvDir)
    }
}

# Dependencies, same set as winbuild.bat. Installing the project also pulls in cx_Freeze (see setup.py).
Invoke-Checked $Python @('-m', 'pip', 'install', '-U', 'pip', 'wheel', 'setuptools')
Invoke-Checked $Python @('-m', 'pip', 'install', '-U', 'pymavlink', 'pywin32', 'python-can')
Invoke-Checked $Python @('-m', 'pip', 'install', '-U', '.')

if ($SetupOnly) {
    Write-Host "Build environment is ready: $VenvDir" -ForegroundColor Green
    exit 0
}

# MSI
Invoke-Checked $Python @('pip_sizes.py')
Invoke-Checked $Python @('setup.py', 'bdist_msi')

$Msi = Get-ChildItem -Path (Join-Path $PSScriptRoot 'dist') -Filter '*.msi' |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($null -eq $Msi) {
    throw "The build finished but no .msi was found in dist"
}
Write-Host "Built $($Msi.FullName)" -ForegroundColor Green
