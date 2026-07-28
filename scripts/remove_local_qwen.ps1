[CmdletBinding()]
param(
    [switch]$Execute,
    [switch]$StopOllama
)

$ErrorActionPreference = "Stop"

function Get-OllamaCommand {
    $command = Get-Command ollama -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Команда ollama не найдена. Возможно, Ollama уже удалена."
    }
    return $command.Source
}

$ollama = Get-OllamaCommand
$patterns = @("qwen", "huihui")

Write-Host "Поиск локальных Qwen/Huihui моделей..."
$listOutput = & $ollama list 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Не удалось получить список Ollama-моделей: $listOutput"
}

$models = @()
foreach ($line in $listOutput | Select-Object -Skip 1) {
    $name = (($line -split "\s+")[0]).Trim()
    if ([string]::IsNullOrWhiteSpace($name)) {
        continue
    }
    $lower = $name.ToLowerInvariant()
    if ($patterns | Where-Object { $lower.Contains($_) }) {
        $models += $name
    }
}
$models = $models | Sort-Object -Unique

if (-not $models) {
    Write-Host "Подходящие модели не найдены. Нечего удалять, редкое проявление порядка."
} else {
    Write-Host "Будут удалены только зарегистрированные модели:"
    $models | ForEach-Object { Write-Host "  - $_" }

    if (-not $Execute) {
        Write-Host ""
        Write-Host "Это предварительный просмотр. После проверки серверного RP и VL запустите:"
        Write-Host "  powershell -ExecutionPolicy Bypass -File scripts/remove_local_qwen.ps1 -Execute"
        exit 0
    }

    foreach ($model in $models) {
        Write-Host "Удаление $model..."
        & $ollama rm $model
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось удалить модель $model."
        }
    }
}

if ($StopOllama) {
    Write-Host "Остановка процессов Ollama..."
    Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force
}

$storageCandidates = @(
    $env:OLLAMA_MODELS,
    (Join-Path $env:USERPROFILE ".ollama\models"),
    "E:\OllamaModels",
    "E:\OllamaModels\models"
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique

Write-Host ""
Write-Host "Каталоги, которые нужно проверить вручную после резервного окна:"
foreach ($path in $storageCandidates) {
    if (Test-Path -LiteralPath $path) {
        $size = (Get-ChildItem -LiteralPath $path -File -Recurse -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
        $sizeGb = if ($null -eq $size) { 0 } else { [math]::Round($size / 1GB, 2) }
        Write-Host "  - $path ($sizeGb GB)"
    }
}

Write-Host "Скрипт намеренно не удаляет каталоги целиком: там могут лежать чужие модели и manifests."
