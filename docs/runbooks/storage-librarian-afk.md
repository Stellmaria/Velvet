# Storage Librarian AFK new-only

## Цель

AFK-режим анализирует только новые разрешённые объекты Telegram Storage через локальный `qwen3.5:9b-q4_K_M`. Старый архив не ставится в очередь автоматически и не переанализируется после смены версии модели.

## Безопасная модель работы

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

## Включение

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

Затем включить new-only AFK:

```bash
sudo bash deploy/hermes-librarian/enable_afk.sh
```

Скрипт:

1. читает максимальный текущий `telegram_storage_objects.id` через работающий bot container;
2. записывает его как `STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID`;
3. включает `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true`;
4. задаёт один объект за цикл и интервал 300 секунд;
5. пересоздаёт только основной bot.

Все объекты с ID меньше либо равным cutoff автоматически игнорируются. Повторный запуск скрипта намеренно устанавливает новый cutoff на текущую вершину архива.

## Отключение

```bash
sudo bash deploy/hermes-librarian/disable_afk.sh
```

Отключается только background scheduler. Локальный Ollama, Librarian API, индекс и ручные команды остаются доступны.

## Переменные

```dotenv
STORAGE_LIBRARIAN_AUTO_ENQUEUE=true
STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID=2200
STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS=diagnostics,releases
STORAGE_LIBRARIAN_AUTO_BATCH_SIZE=1
STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS=300
```

`AUTO_MIN_OBJECT_ID=0` при включённом AFK считается ошибкой конфигурации. Scheduler не стартует, вместо того чтобы случайно съесть весь архив. Наконец-то fail-closed используется не только в презентациях про безопасность.

## Нагрузка

Scheduler выполняет не более одного анализа за цикл. При стандартном интервале 300 секунд верхняя граница составляет 12 объектов в час, но реальная скорость дополнительно ограничена CPU-only inference и очередью.

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

1. отключить AFK;
2. увеличить интервал;
3. оставить batch равным 1;
4. при необходимости перейти на 4B-модель отдельным PR.

## Отчёты и ошибки

Успешный анализ публикуется в `Hermes Reports` без звукового уведомления.

После исчерпания всех попыток терминальная ошибка также публикуется в `Hermes Reports`, но уже с уведомлением. Сообщение содержит Storage ID, категорию/имя файла при наличии и очищенную причину. Секреты, source excerpt и raw response не публикуются.

Librarian не выполняет `restart`, `update`, `rollback`, не создаёт PR и не получает инструменты Каэля.

## Каэль

AFK Librarian не вызывает Каэля на каждый найденный warning. Это сохраняет нулевую стоимость локального анализа и не создаёт автоматических действий по выводам модели.

За live-состоянием сервера следит отдельный Hermes incident monitor. Он вызывает Каэля при подтверждённых lifecycle-инцидентах и имеет собственные cooldown/dedup правила. Архивный отчёт из `Hermes Reports` передаётся Каэлю только по явному решению владельца.

## Smoke-test

После включения:

1. выполнить `/storage_librarian`;
2. убедиться, что статус показывает `AFK new-only: активен` и ненулевой cutoff;
3. дождаться появления нового небольшого diagnostic/release объекта;
4. не запускать `/storage_analyze` для него вручную;
5. проверить появление результата в `/storage_digest 1` и `Hermes Reports`;
6. убедиться, что старые ID ниже cutoff не появились в очереди.
