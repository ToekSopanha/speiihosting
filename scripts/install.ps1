param([string]$Source = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$SpeiiPython = $null
foreach ($Candidate in @('python3', 'python', 'py')) {
    if (Get-Command $Candidate -ErrorAction SilentlyContinue) {
        & $Candidate -c 'import sys; raise SystemExit(sys.version_info < (3,10))' 2>$null
        if ($LASTEXITCODE -eq 0) { $SpeiiPython = $Candidate; break }
    }
}
if (-not $SpeiiPython) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Python 3.10+ and rerun.' }
    & winget install --id Python.Python.3.12 --exact --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
    $SpeiiPython = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python312/python.exe'
    if (-not (Test-Path $SpeiiPython)) { throw 'Reopen PowerShell and rerun the installer.' }
}
$SpeiiHome = if ($env:SPEIIHOSTING_HOME) { $env:SPEIIHOSTING_HOME } else { Join-Path $env:USERPROFILE '.speiihosting' }
$SpeiiEnvironment = Join-Path $SpeiiHome 'cli-venv'
& $SpeiiPython -m venv $SpeiiEnvironment
if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
$SpeiiInterpreter = Join-Path $SpeiiEnvironment 'Scripts/python.exe'
& $SpeiiInterpreter -m pip install --upgrade $Source
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
$SpeiiScripts = Join-Path $SpeiiEnvironment 'Scripts'
$UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($UserPath -split ';') -notcontains $SpeiiScripts) {
    [Environment]::SetEnvironmentVariable('Path', "$UserPath;$SpeiiScripts", 'User')
}
Write-Host 'Installed. Reopen PowerShell and run speiihos init.'
