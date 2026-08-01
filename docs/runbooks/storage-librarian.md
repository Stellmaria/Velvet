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

Velvet Librarian Hermes
  ├─ отдельный /opt/data, SOUL.md и AGENTS.md
  ├─ отдельный API key
  ├─ без Telegram/GitHub token
  ├─ без host port
  ├─ без terminal/file/web/browser/memory/delegation/code tools
  └─ custom model endpoint: http://ollama-librarian:11434/v1

Ollama Librarian
  ├─ только внутренняя сеть velvet_backend
  ├─ qwen3.5:9b-q4_K_M
  ├─ alias velvet-librarian-local:v1
  ├─ context 65536
  └─ отдельный persistent Docker volume
```

Cloud fallback намеренно отсутствует. Если локальная модель недоступна, задача завершается явной ошибкой и не расходует провайдерские токены.

## Защищённые категории

Никогда не анализируются:

- `backups`;
- зашифрованные объекты;
- `watermarks`;
- результаты `analysis`, чтобы исключить рекурсию;
- файлы выше настроенного лимита;
- неподдерживаемые бинарные форматы.

Перед анализом:

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
STORAGE_LIBRARIAN_HERMES_MEMORY_LIMIT=2g
STORAGE_LIBRARIAN_HERMES_CPU_LIMIT=1.0

STORAGE_LIBRARIAN_LOCAL_MODEL=velvet-librarian-local:v1
STORAGE_LIBRARIAN_LOCAL_BASE_URL=http://ollama-librarian:11434/v1
STORAGE_LIBRARIAN_LOCAL_CONTEXT_LENGTH=65536
STORAGE_LIBRARIAN_OLLAMA_IMAGE=ollama/ollama:0.32.3
STORAGE_LIBRARIAN_OLLAMA_MEMORY_LIMIT=14g
STORAGE_LIBRARIAN_OLLAMA_CPU_LIMIT=6.0
STORAGE_LIBRARIAN_OLLAMA_KEEP_ALIVE=30m
STORAGE_LIBRARIAN_OLLAMA_VOLUME=velvet_librarian_ollama

STORAGE_LIBRARIAN_ENABLED=false
STORAGE_LIBRARIAN_AUTO_ENQUEUE=false
STORAGE_LIBRARIAN_PUBLISH_REPORTS=true
STORAGE_LIBRARIAN_ALLOWED_KINDS=diagnostics,exports,codex,releases,rework,inbox
STORAGE_LIBRARIAN_ANALYZER_VERSION=velvet-librarian:qwen3.5-9b-local:v3
STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS=300
STORAGE_LIBRARIAN_POLL_INTERVAL_SECONDS=2
STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS=900
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

Затем установить отдельный Librarian runtime:

```bash
sudo bash deploy/hermes-librarian/install.sh
```

Первый запуск:

1. подготавливает local-only Hermes profile;
2. запускает `ollama-librarian` без host port;
3. скачивает `qwen3.5:9b-q4_K_M` размером около 6,6 ГБ;
4. создаёт `velvet-librarian-local:v1` с контекстом 65 536;
5. запускает `librarian-hermes`;
6. пересоздаёт основной bot;
7. проверяет bot → Librarian health.

На CPU-only сервере первый pull и запуск могут занять несколько минут. `velvet-librarian.service` имеет `TimeoutStartSec=1800`.

Installer также:

- генерирует dedicated API key без вывода значения;
- устанавливает отдельные `SOUL.md` и `AGENTS.md`;
- задаёт пустой API tool whitelist и глобальный deny-list;
- удаляет все cloud fallback providers из профиля;
- устанавливает версию `velvet-librarian:qwen3.5-9b-local:v3`;
- включает публикацию в Hermes Reports;
- сохраняет `STORAGE_LIBRARIAN_AUTO_ENQUEUE` под отдельным ручным контролем.

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

Ожидаются два healthy-контейнера:

- `ollama-librarian`;
- `librarian-hermes`.

Проверка модели:

```bash
sudo docker compose \
  --env-file .env.server \
  -f deploy/hermes-librarian/compose.yaml \
  exec -T ollama-librarian \
  ollama show velvet-librarian-local:v1
```

Проверка отсутствия публичного порта:

```bash
sudo docker inspect ollama-librarian \
  --format '{{json .NetworkSettings.Ports}}'
```

Не должно быть host binding для `11434`.

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

## Поиск `/storage_ask`

Первичный SQL-поиск сохраняется для точных совпадений. Если полная фраза не найдена, application layer:

1. читает до 50 последних анализов за 365 дней;
2. удаляет служебные слова;
3. нормализует распространённые русские и английские окончания;
4. ранжирует summary, tags, entities, action items и имя объекта;
5. передаёт до восьми релевантных источников локальной модели.

Поэтому запрос `какие ошибки и предупреждения повторялись?` способен сопоставить форму `ошибки` с `ошибкой`/`ошибок`. Случайные последние записи без совпадений не подставляются.

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

Автоматическую очередь включать только после проверки качества и длительности локального анализа:

```dotenv
STORAGE_LIBRARIAN_AUTO_ENQUEUE=true
```

## Наблюдение за ресурсами

```bash
sudo docker stats --no-stream \
  ollama-librarian \
  librarian-hermes

sudo docker compose \
  --env-file .env.server \
  -f deploy/hermes-librarian/compose.yaml \
  exec -T ollama-librarian ollama ps
```

Если система начинает использовать swap во время коротких логов, снизить контекст или перейти на `qwen3.5:4b`. Для текущего VPS с 23 ГБ RAM и 8 vCPU целевой вариант — 9B Q4.

## Backup

Модель хранится в Docker volume и может быть повторно скачана, поэтому включать её в PostgreSQL backup не требуется. Анализы и очередь остаются в существующих таблицах PostgreSQL и попадают в обычный backup Velvet.

## Ограничения

- CPU-only inference медленнее облачного, особенно на больших объектах;
- PDF, изображения, видео, RAR и TAR не анализируются;
- Inbox поддержан как storage kind, но отдельный UX ручной загрузки остаётся следующим срезом;
- публикация отчёта не является отдельным Storage object и не запускает рекурсивный анализ;
- mass auto-enqueue запрещён до smoke-test качества и нагрузки.
