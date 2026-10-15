# Shared by run.bat, build.bat and run_gate.bat. Only the selected executable
# goes to stdout; diagnostics go to stderr so FOR /F cannot mistake them for a path.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$probe = 'import sys; sys.exit(1) if sys.version_info[:2] != (3, 13) or sys.maxsize <= 2**32 else print(sys.executable)'

function Find-CompatiblePython {
    param([string]$Candidate, [string[]]$PrefixArgs = @())
    try {
        $output = @(& $Candidate @PrefixArgs -I -c $probe 2>$null)
        if ($LASTEXITCODE -eq 0 -and $output.Count -eq 1) {
            $resolved = [string]$output[0]
            if (Test-Path -LiteralPath $resolved -PathType Leaf) {
                return $resolved
            }
        }
    } catch {
        # Missing executables and rejected launcher versions are expected probes.
    }
    return $null
}

function Use-RequiredPython {
    param([string]$Candidate, [string]$Source)
    $resolved = Find-CompatiblePython $Candidate
    if ($resolved) {
        Write-Output $resolved
        exit 0
    }
    [Console]::Error.WriteLine("[ERROR] $Source must point to a working 64-bit Python 3.13 executable. Fix it or remove the override/environment before retrying.")
    exit 1
}

if ($env:ODC_PYTHON) {
    Use-RequiredPython $env:ODC_PYTHON 'ODC_PYTHON'
}
if ($env:VIRTUAL_ENV) {
    Use-RequiredPython (Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe') 'VIRTUAL_ENV'
}
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $projectPython -PathType Leaf) {
    Use-RequiredPython $projectPython 'Project .venv'
}

$launcher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($launcher) {
    $resolved = Find-CompatiblePython $launcher.Source @('-3.13')
    if ($resolved) { Write-Output $resolved; exit 0 }
}
foreach ($command in @(Get-Command python -All -CommandType Application -ErrorAction SilentlyContinue)) {
    # Windows Store aliases may open the Store instead of running Python.
    if ($command.Source -like '*\Microsoft\WindowsApps\*') { continue }
    $resolved = Find-CompatiblePython $command.Source
    if ($resolved) { Write-Output $resolved; exit 0 }
}
if ($env:LOCALAPPDATA) {
    $resolved = Find-CompatiblePython (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe')
    if ($resolved) { Write-Output $resolved; exit 0 }
}
[Console]::Error.WriteLine('[ERROR] No compatible Python 3.13 (64-bit) found. Install it, or set ODC_PYTHON to the full path of its python.exe. Dependencies must be installed in that same interpreter.')
exit 1
