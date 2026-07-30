# Velvet remote Krita worker

Windows-worker отделяет Krita от основного Velvet Bot на VPS. Бот и PostgreSQL работают на Linux, а локальная Krita получает только одну арендованную watermark-задачу, исходник и snapshot логотипа.

## Безопасная схема подключения

API контейнера публикуется только на loopback VPS. На Windows откройте SSH-туннель:

```powershell
ssh -N -L 8766:127.0.0.1:8766 velvet@SERVER_IP
```

Worker обращается к `http://127.0.0.1:8766`. Публичный порт и входящее подключение к Windows не нужны.

## Переменные Windows

```powershell
$env:VELVET_KRITA_API_URL = "http://127.0.0.1:8766"
$env:VELVET_KRITA_WORKER_TOKEN = "тот же случайный секрет, что на VPS"
$env:VELVET_KRITA_WORKER_ID = "krita-windows-01"
$env:VELVET_KRITA_BRIDGE_DIR = "E:\VelvetKritaBridge"
```

Krita должна использовать тот же локальный bridge-каталог. Запуск:

```powershell
powershell -ExecutionPolicy Bypass -File tools\krita_worker\run_worker.ps1
```

Однократная проверка без постоянного polling:

```powershell
python -m tools.krita_worker.worker --once
```

## Поведение при отключении компьютера

Активный lease продлевается heartbeat-сообщениями. Если worker или SSH-туннель исчезает, lease истекает и revision возвращается в `pending`. Основной бот, архив, генерации и остальные очереди продолжают работать.

## Что worker не получает

- `BOT_TOKEN`;
- `DATABASE_URL`;
- ключи Kie/GRS/RP/VL;
- production `.env`;
- доступ к Docker или Supervisor.
