param(
    [string]$TaskName = "VelvetSupervisor",
    [string]$ProjectDir = "",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectDir)) {
    $ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} else {
    $ProjectDir = (Resolve-Path $ProjectDir).Path
}

Set-Location $ProjectDir

$dirty = (& git status --porcelain)
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось проверить состояние Git в $ProjectDir."
}
if ($dirty) {
    throw "В проекте есть локальные изменения. Сохраните или уберите их перед обновлением Supervisor.`n$dirty"
}

& git switch main
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось переключиться на ветку main."
}

& git fetch origin
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось получить origin/main."
}

& git merge-base --is-ancestor HEAD origin/main
if ($LASTEXITCODE -ne 0) {
    throw "Локальная main содержит отдельные коммиты или разошлась с origin/main. Автоматическое обновление остановлено."
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

# Stop the scheduled parent first. Its child can survive Task Scheduler termination,
# so matching Velvet Python processes are terminated explicitly afterwards.
& schtasks.exe /Query /TN $TaskName *> $null
if ($LASTEXITCODE -eq 0) {
    & schtasks.exe /End /TN $TaskName *> $null
}
Start-Sleep -Seconds 2

$escapedProject = [Regex]::Escape($ProjectDir)
$velvetProcesses = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -ieq "python.exe" -or $_.Name -ieq "pythonw.exe") -and
    -not [string]::IsNullOrWhiteSpace($_.CommandLine) -and
    ($_.CommandLine -match "velvet_supervisor" -or $_.CommandLine -match $escapedProject)
}
foreach ($process in $velvetProcesses) {
    Write-Host "Stopping stale Velvet process PID=$($process.ProcessId): $($process.CommandLine)"
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

& git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось выполнить fast-forward обновление main."
}

$Head = (& git rev-parse --short HEAD).Trim()
$RegisterScript = (Resolve-Path (Join-Path $PSScriptRoot "register_supervisor_task.ps1")).Path

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RegisterScript `
    -TaskName $TaskName `
    -ProjectDir $ProjectDir `
    -PythonExe $PythonExe
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось заново зарегистрировать Supervisor."
}

Start-Sleep -Seconds 3
Write-Host "Velvet Supervisor обновлён и запущен."
Write-Host "ProjectDir: $ProjectDir"
Write-Host "Git HEAD: $Head"
Write-Host "TaskName: $TaskName"
Write-Host "Проверьте новое сообщение 'Velvet Supervisor запущен': в нём должны совпадать путь, Git HEAD и UTF-8-параметры."
