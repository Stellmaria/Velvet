# Storage Librarian background modes

## Цель

Storage Librarian поддерживает два явно разделённых фоновых режима через локальный Ollama:

1. `AFK new-only` для новых объектов после зафиксированного cutoff;
2. `full-archive backfill` для постепенного анализа всего поддерживаемого Telegram Storage.

Оба режима остаются bounded: по умолчанию обрабатывается один объект за цикл, inference выполняется локально, encrypted/unsupported/oversized объекты не отправляются в анализ.

## AFK new-only

Безопасная модель работы:

```text
новый Storage object
        ↓
ID выше зафиксированного cutoff
        ↓
разрешённая AFK-категория
        ↓
не encrypted, не backup/watermark/analysis
        ↓
один объект за цикл
        ↓
локальный Ollama → PostgreSQL → Hermes Reports
```

По умолчанию AFK разрешены только:

- `diagnostics`;
- `releases`.

Ручные команды `/storage_analyze`, `/storage_digest` и `/storage_ask` продолжают работать для полного ручного allowlist.

### Включение new-only

Сначала подтвердить local runtime:

```bash
cd /srv/velvet
sudo docker compose \
  --env-file .env.server \
  -f deploy/hermes-librarian/compose.yaml \
  ps

sudo docker compose \
  --env-file .env.server \
  -f deploy/hermes-librarian/compose.yaml \
  exec -T ollama-librarian ollama list
```

Затем:

```bash
sudo bash deploy/hermes-librarian/enable_afk.sh
```

Скрипт:

1. читает максимальный текущий `telegram_storage_objects.id` через работающий bot container;
2. записывает его как `STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID` cutoff;
3. включает `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true`;
4. явно оставляет `STORAGE_LIBRARIAN_AUTO_BACKFILL=false`;
5. задаёт один объект за цикл и интервал 300 секунд;
6. пересоздаёт только основной bot.

Все объекты с ID меньше либо равным cutoff автоматически игнорируются. Повторный запуск скрипта намеренно устанавливает новый cutoff на текущую вершину архива.

## Full-archive backfill

Полный backfill является отдельным явным opt-in. Он не маскируется под new-only и не ставит весь архив в очередь одной транзакцией.

```bash
cd /srv/velvet
sudo bash deploy/hermes-librarian/enable_full_archive.sh
```

Скрипт fail-closed проверяет, что analysis route остаётся локальным:

```text
http://ollama-librarian:11434
```

После включения устанавливается:

```dotenv
STORAGE_LIBRARIAN_ENABLED=true
STORAGE_LIBRARIAN_AUTO_ENQUEUE=true
STORAGE_LIBRARIAN_AUTO_BACKFILL=true
STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID=0
STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS=diagnostics,codex,rework,inbox,exports,releases
STORAGE_LIBRARIAN_AUTO_BATCH_SIZE=1
STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS=60
```

В этом режиме scheduler использует bounded `enqueue_pending(..., limit=batch_size)` и затем выполняет одну `process_once(auto_enqueue=false)` итерацию. Поэтому архив заполняется постепенно, без массового enqueue. Объекты без анализа и объекты со старой `analyzer_version` проходят через текущий локальный analyzer. Терминальные failed jobs не сбрасываются бесконечно автоматически.

`AUTO_MIN_OBJECT_ID=0` допустим только вместе с `AUTO_BACKFILL=true`. В new-only режиме нулевой cutoff по-прежнему считается ошибкой конфигурации.

### Что означает «весь архив»

Backfill охватывает все категории из текущего `STORAGE_LIBRARIAN_ALLOWED_KINDS`, которые Librarian умеет безопасно загрузить. По текущему production contract это `diagnostics,codex,rework,inbox,exports,releases`.

Автоматически исключаются:

- encrypted объекты;
- объекты больше `STORAGE_LIBRARIAN_MAX_OBJECT_BYTES`;
- неподдерживаемый content;
- backup/watermark/analysis kinds, если они не входят в allowlist;
- vision-only содержимое, пока image bytes path не завершён отдельной задачей.

Это ограничение намеренное: «full archive» не означает обход существующих security/content boundaries.

## Отключение

Оба фоновых режима выключаются одинаково:

```bash
sudo bash deploy/hermes-librarian/disable_afk.sh
```

Скрипт устанавливает:

```dotenv
STORAGE_LIBRARIAN_AUTO_ENQUEUE=false
STORAGE_LIBRARIAN_AUTO_BACKFILL=false
```

Локальный Ollama, Librarian API, индекс и ручные команды остаются доступны.

## Нагрузка

New-only по умолчанию работает раз в 300 секунд. Full-archive по умолчанию использует batch `1` и интервал 60 секунд, но inference выполняется синхронно, поэтому следующий цикл начинается только после завершения текущего анализа и паузы.

Рекомендуемая проверка:

```bash
sudo docker stats --no-stream \
  velvet-librarian-ollama-librarian-1 \
  velvet-librarian-librarian-hermes-1 \
  velvet-bot-1

free -h
swapon --show
```

При устойчивом использовании swap:

1. выполнить `disable_afk.sh`;
2. увеличить интервал;
3. оставить batch равным `1`;
4. не расширять concurrency ради скорости.

## Отчёты и ошибки

Успешный анализ публикуется в `Hermes Reports` без звукового уведомления, если `STORAGE_LIBRARIAN_PUBLISH_REPORTS=true`.

После исчерпания всех попыток терминальная ошибка также публикуется в `Hermes Reports`, но уже с уведомлением. Сообщение содержит Storage ID, категорию/имя файла при наличии и очищенную причину. Секреты, source excerpt и raw response не публикуются.

Librarian не выполняет `restart`, `update`, `rollback`, не создаёт PR и не получает инструменты Каэля.

## Каэль и Arthur

Arthur остаётся owner-only Telegram интерфейсом для статуса, ручного анализа и результатов. Фоновый scheduler живёт в основном Velvet bot process; analysis client при этом остаётся `OllamaStorageAnalysisClient`. В Arthur container `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` остаётся жёстко зафиксированным, чтобы второй scheduler не появился случайно.

AFK/backfill не вызывает Каэля на каждый найденный warning. За live-состоянием сервера следит отдельный Hermes incident monitor.

## Smoke-test

После включения new-only:

1. выполнить `/storage_librarian`;
2. убедиться, что статус показывает `AFK new-only: активен` и ненулевой cutoff;
3. дождаться нового небольшого diagnostic/release объекта;
4. проверить результат в `/storage_digest 1` и `Hermes Reports`.

После включения full-archive:

1. выполнить `/storage_librarian`;
2. убедиться, что статус показывает `AFK full-archive: активен` и `локальный Ollama`;
3. проверить, что `В очереди`/`Готово` меняются постепенно, а не скачком на весь архив;
4. проверить `docker stats` и отсутствие устойчивого swap pressure;
5. при необходимости остановить backfill через `disable_afk.sh`.
