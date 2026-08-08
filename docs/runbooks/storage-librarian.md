# Storage Librarian

## Назначение

Velvet Librarian — отдельная внутренняя Hermes-сущность для каталогизации разрешённых объектов существующего Telegram Storage. Он не создаёт второй Telegram-архив, не владеет `telegram_file_id` и не использует память либо инструменты Каэля.

Архитектура:

```text
Velvet bot
  ├─ владеет Telegram Storage и file_id
  ├─ проверяет multipart/SHA256
  ├─ очищает чувствительные строки
  ├─ отправляет bounded text напрямую в private Ollama /api/chat
  ├─ использует Hermes Runs API только для /storage_ask
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
  ├─ text: qwen3:4b-instruct → velvet-librarian-text:v1, context 8192
  ├─ vision: qwen3.5:9b-q4_K_M → velvet-librarian-vision:v1, context 16384
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

STORAGE_LIBRARIAN_OLLAMA_BASE_URL=http://ollama-librarian:11434
STORAGE_LIBRARIAN_TEXT_MODEL=velvet-librarian-text:v1
STORAGE_LIBRARIAN_VISION_MODEL=velvet-librarian-vision:v1
STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH=8192
STORAGE_LIBRARIAN_TEXT_MAX_OUTPUT_TOKENS=384
STORAGE_LIBRARIAN_VISION_CONTEXT_LENGTH=16384
STORAGE_LIBRARIAN_VISION_MAX_OUTPUT_TOKENS=640
STORAGE_LIBRARIAN_OLLAMA_IMAGE=ollama/ollama:0.32.3
STORAGE_LIBRARIAN_OLLAMA_MEMORY_LIMIT=14g
STORAGE_LIBRARIAN_OLLAMA_CPU_LIMIT=6.0
STORAGE_LIBRARIAN_OLLAMA_KEEP_ALIVE=5m
STORAGE_LIBRARIAN_OLLAMA_VOLUME=velvet_librarian_ollama

STORAGE_LIBRARIAN_ENABLED=false
STORAGE_LIBRARIAN_AUTO_ENQUEUE=false
STORAGE_LIBRARIAN_PUBLISH_REPORTS=true
STORAGE_LIBRARIAN_ALLOWED_KINDS=diagnostics,exports,codex,releases,rework,inbox
STORAGE_LIBRARIAN_ANALYZER_VERSION=velvet-librarian:qwen3-4b-text:v4
STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS=300
STORAGE_LIBRARIAN_POLL_INTERVAL_SECONDS=2
STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS=720
STORAGE_LIBRARIAN_MAX_OBJECT_BYTES=12582912
# STORAGE_LIBRARIAN_MAX_TEXT_CHARS=11520
STORAGE_LIBRARIAN_MAX_ZIP_ENTRIES=40
STORAGE_LIBRARIAN_MAX_ATTEMPTS=3
```

`STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS` имеет effective CPU floor `720` секунд. Более низкий legacy override безопасно поднимается до floor в application settings, а большее значение до `1800` секунд сохраняется. Это нужно потому, что timeout покрывает весь Ollama request wall-clock, включая prompt evaluation, generation и ожидание локального single slot.

`STORAGE_LIBRARIAN_MAX_TEXT_CHARS` намеренно является необязательным tighter cap. Если переменная не задана, приложение вычисляет безопасный source-envelope limit из `STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH` и `STORAGE_LIBRARIAN_TEXT_MAX_OUTPUT_TOKENS`. Для стандартных `8192/384` single-shot limit равен `11520`: из context резервируются output и `1024` токена system/schema overhead, применяется консервативная оценка `2 chars/token`, затем ещё `2048` символов резервируются под analysis wrapper. Явный меньший override сохраняется как tighter cap. Legacy завышенное значение, включая ранее использовавшееся `120000`, безопасно ограничивается derived limit.

Source больше single-shot limit обрабатывается bounded hierarchical path. Исходный текст делится на детерминированные contiguous chunks без потери символов; каждый chunk последовательно анализируется тем же local Ollama client, после чего выполняется одна bounded synthesis по ordered chunk summaries. По умолчанию допускается до `12` chunks и до `13` inference calls на объект. Chunk wrapper резервирует `512` символов, поэтому для canonical `8192/384` theoretical hard source cap равен `(11520 - 512) * 12 = 132096` символов. Значение `STORAGE_LIBRARIAN_MAX_CHUNK_SOURCE_CHARS` может только дополнительно уменьшить этот предел. Source выше hard cap завершается terminal error до inference; silent truncation запрещён.

Все supported Storage worker paths используют один PostgreSQL transaction advisory claim gate. Пока любой `telegram_storage_analysis_jobs` row имеет status `running`, другой main/AFK/Arthur claimant не переводит следующий queued job в `running`. Advisory lock удерживается только на время claim transaction, а не во время inference; orphaned `running` row освобождается существующим stale-recovery path. Это не меняет `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` для Arthur и не добавляет cloud fallback.

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
3. скачивает `qwen3:4b-instruct` и `qwen3.5:9b-q4_K_M`;
4. пересоздаёт aliases `velvet-librarian-text:v1` и `velvet-librarian-vision:v1`;
5. запускает `librarian-hermes`;
6. пересоздаёт основной bot;
7. проверяет bot → Librarian health.

На CPU-only сервере первый pull и запуск могут занять несколько минут. `velvet-librarian.service` имеет `TimeoutStartSec=1800`.

Installer также:

- генерирует dedicated API key без вывода значения;
- устанавливает отдельные `SOUL.md` и `AGENTS.md`;
- задаёт пустой API tool whitelist и глобальный deny-list;
- удаляет все cloud fallback providers из профиля;
- устанавливает версию `velvet-librarian:qwen3-4b-text:v4`;
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
  ollama show velvet-librarian-text:v1

sudo docker compose \
  --env-file .env.server \
  -f deploy/hermes-librarian/compose.yaml \
  exec -T ollama-librarian \
  ollama show velvet-librarian-vision:v1
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
5. передаёт до восьми релевантных источников Hermes answer client.

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

Для smoke-test выбрать небольшой TXT, JSON или log. Не выбирать backup, encrypted object, изображение, видео или большой ZIP. Vision alias подготовлен только для будущего pipeline: image support не завершена, пока приложение не передаёт image bytes. После успешного анализа в теме `Hermes Reports` должно появиться сообщение с Storage ID, резюме, тегами и действиями.

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

Если система начинает использовать swap во время коротких логов, не включать массовую очередь и проверить фактические `num_ctx`, время и число одновременно загруженных aliases.

## Backup

Модель хранится в Docker volume и может быть повторно скачана, поэтому включать её в PostgreSQL backup не требуется. Анализы и очередь остаются в существующих таблицах PostgreSQL и попадают в обычный backup Velvet.

## Ограничения

- CPU-only inference медленнее облачного, особенно на больших объектах;
- PDF, изображения, видео, RAR и TAR не анализируются; наличие vision alias само по себе image support не добавляет;
- Inbox поддержан как storage kind, но отдельный UX ручной загрузки остаётся следующим срезом;
- публикация отчёта не является отдельным Storage object и не запускает рекурсивный анализ;
- mass auto-enqueue запрещён до smoke-test качества и нагрузки.