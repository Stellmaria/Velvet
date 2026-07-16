param(
    [string]$TaskName = "VelvetSupervisor",
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

$RunScript = (Resolve-Path (Join-Path $PSScriptRoot "run_supervisor.ps1")).Path
$TaskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$RunScript`" -ProjectDir `"$ProjectDir`" -PythonExe `"$PythonExe`""

& schtasks.exe /Create /TN $TaskName /TR $TaskCommand /SC ONLOGON /RL LIMITED /F
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось зарегистрировать задачу $TaskName."
}

& schtasks.exe /Run /TN $TaskName
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Задача создана, но её не удалось запустить автоматически."
}

Write-Host "Задача $TaskName зарегистрирована."
Write-Host "Проверка: schtasks /Query /TN $TaskName /V /FO LIST"
