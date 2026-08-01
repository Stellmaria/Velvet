# Storage Librarian

## Назначение

Velvet Librarian — отдельная внутренняя Hermes-сущность для каталогизации разрешённых объектов существующего Telegram Storage. Он не создаёт второй Telegram-архив, не владеет `telegram_file_id` и не использует память либо инструменты Каэля.

Архитектура:

```text
Velvet bot
  ├─ владеет Telegram Storage и file_id
  ├─ проверяет multipart/SHA256
  ├─ очищает чувствительные строки
  ├─ отправляет bounded text во внутренний Runs API
  └─ публикует готовое резюме в Hermes Reports

Velvet Librarian
  ├─ отдельный /opt/data, SOUL.md и AGENTS.md
  ├─ отдельный API key
  ├─ без Telegram/GitHub token
  ├─ без host port
  └─ без terminal/file/web/browser/memory/delegation/code tools
```

## Защищённые категории

Никогда не анализируются:

- `backups`;
- зашифрованные объекты;
- `watermarks`;
- результаты `analysis`, чтобы исключить рекурсию;
- файлы выше настроенного лимита;
- неподдерживаемые бинарные форматы.

Перед отправкой:

- multipart собирается в памяти;
- SHA256 каждой части и итогового объекта проверяется;
- ZIP/DOCX читаются без распаковки на диск и с лимитом распакованных байтов;
- токены, API keys, DSN и пароли очищаются;
- содержимое помечается как данные, а не инструкции.

## Telegram topics

```dotenv
STORAGE_THREAD_INBOX=2476
STORAGE_THREAD_ANALYSIS=2478
```

- `2476` — Inbox Unclassified;
- `2478` — Hermes Reports.

Готовый анализ сохраняется в PostgreSQL. При `STORAGE_LIBRARIAN_PUBLISH_REPORTS=true` краткий отчёт дополнительно публикуется ботом Velvet в `Hermes Reports`. Ошибка публикации не отменяет сохранённый анализ и фиксируется в логах.

## Основные переменные

```dotenv
STORAGE_LIBRARIAN_HERMES_BASE_URL=http://librarian-hermes:8642
STORAGE_LIBRARIAN_HERMES_API_KEY=<отдельный ключ, не ключ Каэля>

STORAGE_LIBRARIAN_ENABLED=false
STORAGE_LIBRARIAN_AUTO_ENQUEUE=false
STORAGE_LIBRARIAN_PUBLISH_REPORTS=true
STORAGE_LIBRARIAN_ALLOWED_KINDS=diagnostics,exports,codex,releases,rework,inbox
STORAGE_LIBRARIAN_ANALYZER_VERSION=velvet-librarian:v2
STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS=300
STORAGE_LIBRARIAN_POLL_INTERVAL_SECONDS=2
STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS=300
STORAGE_LIBRARIAN_MAX_OBJECT_BYTES=12582912
STORAGE_LIBRARIAN_MAX_TEXT_CHARS=120000
STORAGE_LIBRARIAN_MAX_ZIP_ENTRIES=40
STORAGE_LIBRARIAN_MAX_ATTEMPTS=3
```

Generic `HERMES_BASE_URL`/`HERMES_API_KEY` принадлежат Каэлю и incident/Supervisor-интеграции. Storage Librarian использует dedicated variables и не должен подменять основной Hermes endpoint.

## Установка сущностей

Сначала установить Каэля и coder-сущности:

```bash
cd /srv/velvet
sudo bash deploy/hermes-entities/install.sh
```

Installer:

- ставит `SOUL.kael.md` как `/opt/data/SOUL.md` основного Hermes;
- ставит операторский контракт как `/opt/data/AGENTS.md`;
- устанавливает `runctl.py` для собственных Runs Каэля;
- исправляет владельца `tools/`, `tasks.json` и `tasks.json.lock`;
- ставит отдельные `SOUL.md` кодерам;
- создаёт `.hermes.md` каждого coder workspace из репозиторного `AGENTS.md` и оркестрационного контракта;
- добавляет generated `.hermes.md` в `.git/info/exclude`;
- меняет Telegram display name основного бота на `Kᴀᴇʟ Vᴇʟᴠᴇᴛ`;
- проверяет файлы и ledger от runtime-пользователя `hermes`, а не от root `docker exec`.

Затем установить отдельный Librarian runtime:

```bash
sudo bash deploy/hermes-librarian/install.sh
```

Installer:

- генерирует dedicated API key без вывода значения;
- копирует и ограничивает конфигурацию основного provider routing;
- устанавливает отдельные `SOUL.md` и `AGENTS.md`;
- задаёт пустой API tool whitelist и глобальный deny-list;
- устанавливает `velvet-librarian:v2`;
- включает публикацию в Hermes Reports;
- запускает `velvet-librarian.service`;
- пересоздаёт bot, чтобы он получил dedicated endpoint/key;
- проверяет bot → Librarian health.

## Проверка runtime

```bash
sudo systemctl is-enabled \
  hermes-entities-reconcile.service \
  velvet-librarian.service

sudo systemctl is-active \
  hermes-entities-reconcile.service \
  velvet-librarian.service

sudo docker compose \
  --env-file .env.server \
  -f deploy/hermes-librarian/compose.yaml \
  ps
```

Проверка файлов Каэля:

```bash
sudo docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile agent \
  exec -T hermes \
  /command/s6-setuidgid hermes \
  sh -ceu '
    test "$(id -u)" = "10000"
    test -r /opt/data/SOUL.md
    test -r /opt/data/AGENTS.md
    test -x /opt/data/tools/opsctl.py
    test -x /opt/data/tools/coderctl.py
    test -x /opt/data/tools/runctl.py
    test -w /opt/data/orchestration/tasks.json
    test -w /opt/data/orchestration/tasks.json.lock
  '
```

Проверка таблиц. Маска `\dt *librarian*` неверна: в именах таблиц нет слова `librarian`.

```bash
sudo docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  exec -T postgres sh -ceu '
    psql \
      --username="$POSTGRES_USER" \
      --dbname="$POSTGRES_DB" \
      --command="\dt telegram_storage_analysis*"
  '
```

Ожидаются:

- `telegram_storage_analysis_jobs`;
- `telegram_storage_analysis`.

## Manual-first rollout

Первый запуск выполняется с:

```dotenv
STORAGE_LIBRARIAN_ENABLED=true
STORAGE_LIBRARIAN_AUTO_ENQUEUE=false
STORAGE_LIBRARIAN_PUBLISH_REPORTS=true
```

Команды владельца:

- `/storage_librarian` — статус и очередь;
- `/storage_find diagnostics` — найти небольшой исходный объект;
- `/storage_analyze ID` — ручной анализ;
- `/storage_digest 1` — последние результаты;
- `/storage_ask вопрос` — ответ по проанализированному индексу;
- `/storage_download ID` — получить исходный объект.

Для smoke-test выбрать небольшой TXT, JSON или log. Не выбирать backup, encrypted object, изображение, видео или большой ZIP. После успешного анализа в теме `Hermes Reports` должно появиться сообщение с Storage ID, резюме, тегами и действиями.

Только после проверки качества и расхода можно включать:

```dotenv
STORAGE_LIBRARIAN_AUTO_ENQUEUE=true
```

## Backup

Velvet уже создаёт daily/weekly backup внутренним worker и выгружает валидные dump в Telegram Storage. Дублирующий systemd timer удаляется:

```bash
sudo systemctl disable --now velvet-backup.timer 2>/dev/null || true
sudo rm -f \
  /etc/systemd/system/velvet-backup.service \
  /etc/systemd/system/velvet-backup.timer \
  /usr/local/sbin/velvet-postgres-backup
sudo systemctl daemon-reload
sudo systemctl reset-failed velvet-backup.service 2>/dev/null || true
```

Родной контур проверяется командами `/backup` и `/storage`.

## Ограничения

- PDF, изображения, видео, RAR и TAR не анализируются;
- Inbox поддержан как storage kind, но отдельный UX ручной загрузки остаётся следующим срезом;
- публикация отчёта не является отдельным Storage object и не запускает рекурсивный анализ;
- mass auto-enqueue запрещён до smoke-test и проверки бюджета.
