param(
    [string]$ProjectDir = "",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectDir)) {
    $ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $Candidates = @(
        (Join-Path $ProjectDir ".venv314\Scripts\python.exe"),
        (Join-Path $ProjectDir ".venv\Scripts\python.exe")
    )
    $PythonExe = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if ([string]::IsNullOrWhiteSpace($PythonExe) -or -not (Test-Path $PythonExe)) {
    throw "Python виртуального окружения не найден. Передайте -PythonExe."
}

# Force one Unicode contract for Supervisor itself and every Python child.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Set-Location $ProjectDir
Write-Host "Starting Velvet Supervisor"
Write-Host "ProjectDir: $ProjectDir"
Write-Host "PythonExe: $PythonExe"
Write-Host "PYTHONUTF8: $env:PYTHONUTF8"
Write-Host "PYTHONIOENCODING: $env:PYTHONIOENCODING"

& $PythonExe -m velvet_supervisor
exit $LASTEXITCODE
