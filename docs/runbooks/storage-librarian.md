# Storage Librarian

## Назначение

Storage Librarian индексирует разрешённые объекты существующего Telegram Storage через Hermes Runs API. Он не создаёт второй Telegram-архив и не получает отдельного бота-владельца файлов. Все `telegram_file_id` остаются у Velvet.

## Безопасная модель

Librarian по умолчанию выключен и работает в режиме manual-first.

Никогда не анализируются:

- `backups`;
- зашифрованные объекты;
- `watermarks`;
- результаты `analysis`, чтобы исключить рекурсию;
- файлы выше настроенного лимита;
- неподдерживаемые бинарные форматы.

Перед Hermes:

- multipart-файл собирается в памяти;
- SHA256 каждой части и итогового объекта проверяется;
- ZIP/DOCX читаются без распаковки на диск и с лимитом uncompressed bytes;
- токены, API keys, DSN и пароли очищаются;
- содержимое помечается как данные, а не инструкции;
- Hermes получает запрет на инструменты и опасные действия.

## Переменные окружения

Добавить в `/srv/velvet/.env.server`:

```dotenv
# Новые Telegram topics создаются вручную в закрытом storage-форуме.
# До создания topics значения оставляются пустыми.
STORAGE_THREAD_INBOX=
STORAGE_THREAD_ANALYSIS=

# Сначала включается только ручной smoke-test.
STORAGE_LIBRARIAN_ENABLED=false
STORAGE_LIBRARIAN_AUTO_ENQUEUE=false
STORAGE_LIBRARIAN_ALLOWED_KINDS=diagnostics,exports,codex,releases,rework,inbox
STORAGE_LIBRARIAN_ANALYZER_VERSION=hermes-librarian:v1
STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS=300
STORAGE_LIBRARIAN_POLL_INTERVAL_SECONDS=2
STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS=300
STORAGE_LIBRARIAN_MAX_OBJECT_BYTES=12582912
STORAGE_LIBRARIAN_MAX_TEXT_CHARS=120000
STORAGE_LIBRARIAN_MAX_ZIP_ENTRIES=40
STORAGE_LIBRARIAN_MAX_ATTEMPTS=3
```

Используются существующие:

```dotenv
HERMES_BASE_URL=http://hermes:8642
HERMES_API_KEY=<совпадает с API_SERVER_KEY в .env.hermes>
```

`HERMES_API_KEY`, `STORAGE_ENCRYPTION_SECRET`, токены и DSN не передаются Hermes и не должны печататься в логах.

## Удаление ошибочно созданного systemd backup timer

Velvet уже создаёт daily/weekly backup внутренним worker и выгружает валидные dump в Telegram Storage. Ручной дублирующий timer надо удалить:

```bash
sudo systemctl disable --now velvet-backup.timer 2>/dev/null || true
sudo rm -f \
  /etc/systemd/system/velvet-backup.service \
  /etc/systemd/system/velvet-backup.timer \
  /usr/local/sbin/velvet-postgres-backup
sudo systemctl daemon-reload
sudo systemctl reset-failed velvet-backup.service 2>/dev/null || true
```

После этого проверить родной контур командами владельца `/backup` и `/storage`.

## Развёртывание

1. Создать в закрытом Telegram Storage темы `Inbox Unclassified` и `Hermes Reports`.
2. Записать их реальные `message_thread_id` в `STORAGE_THREAD_INBOX` и `STORAGE_THREAD_ANALYSIS`.
3. Обновить `main` и пересобрать bot.
4. Оставить `STORAGE_LIBRARIAN_ENABLED=false` и убедиться, что bot healthy.
5. Проверить Hermes:

```bash
sudo docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile agent \
  exec -T bot python - <<'PY'
import json
import os
import urllib.request

request = urllib.request.Request(
    os.environ["HERMES_BASE_URL"].rstrip("/") + "/v1/capabilities",
    headers={"Authorization": "Bearer " + os.environ["HERMES_API_KEY"]},
)
with urllib.request.urlopen(request, timeout=15) as response:
    payload = json.load(response)
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
```

6. Включить только ручной режим:

```dotenv
STORAGE_LIBRARIAN_ENABLED=true
STORAGE_LIBRARIAN_AUTO_ENQUEUE=false
```

7. Пересоздать bot и проверить `/storage_librarian`.
8. Найти небольшой текстовый объект через `/storage_find diagnostics` или `/storage_find codex`.
9. Запустить `/storage_analyze ID`.
10. Проверить `/storage_digest 1` и `/storage_ask вопрос`.
11. Только после проверки качества и расхода токенов включать:

```dotenv
STORAGE_LIBRARIAN_AUTO_ENQUEUE=true
```

## Команды владельца

- `/storage_librarian` — статус и очередь;
- `/storage_analyze ID` — приоритетный ручной анализ;
- `/storage_digest 7` — последние результаты;
- `/storage_ask вопрос` — ответ по проанализированному индексу;
- `/storage_find запрос` — поиск исходного storage object;
- `/storage_download ID` — получить исходный объект.

## Ограничения первой версии

- PDF, изображения, видео, RAR и TAR не анализируются;
- `Inbox Unclassified` поддержан как storage kind, но отдельный UX загрузки ручных сообщений остаётся следующим срезом;
- результаты сохраняются в PostgreSQL, а автоматическая публикация отчётов в `Hermes Reports` остаётся следующим срезом;
- массовый auto-enqueue нельзя включать до smoke-test и проверки бюджета.
