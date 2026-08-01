# Сессия: Storage Librarian поверх Telegram Storage

- Дата: 2026-08-01
- ID: `2026-08-01-storage-librarian`
- Линия/фаза: Telegram Storage и Hermes analysis layer
- Статус: `частично`
- Ветка: `agent/storage-librarian`
- Базовый commit: `319cb6c9730302729021e7c7cb210eb756c51b98`

## Перед началом

### Цель

Добавить безопасный слой разбора уже существующего Telegram Storage без второго независимого storage-бота, дублирования файлов и передачи Hermes резервных копий или секретов.

### Исходный контекст

Velvet уже выгружает watermarks, backup, diagnostics, exports, Codex snapshots, releases и rework snapshots в закрытый Telegram-форум, хранит PostgreSQL-индекс объектов и parts, проверяет SHA256 и удаляет локальные копии только после подтверждённой загрузки. На сервере отдельно работают Hermes gateway, operator и coder-контуры. Дополнительно вручную был создан дублирующий systemd backup timer, который завершился ошибкой и не должен заменять встроенный backup worker Velvet.

### Планируемый объём

- расширить storage kinds значениями `inbox` и `analysis`;
- добавить очередь анализа и таблицу результатов;
- реализовать Hermes Runs client с polling terminal status;
- скачать multipart через Telegram только токеном основного Velvet;
- проверять SHA256 parts и итогового объекта;
- безопасно извлекать текст из JSON, logs, text files, ZIP и DOCX;
- исключить backup, encrypted objects, watermarks и recursive analysis;
- очищать токены, DSN и пароли перед Hermes;
- добавить manual-first команды владельца и optional background scheduler;
- закрепить deployment и rollback в runbook;
- добавить контрактные тесты.

### Критерии готовности

- backup и encrypted objects невозможно поставить в Librarian;
- background auto-enqueue выключен по умолчанию;
- `/storage_analyze ID` запускает один приоритетный анализ;
- `/storage_digest` показывает сохранённые summaries;
- `/storage_ask` отвечает только по проанализированному индексу;
- Hermes получает bounded prompt без инструментов и секретов;
- миграции, тесты, type-check и project notes contract проходят;
- production включение выполняется только после ручного smoke-test.

### Риски и ограничения

Hermes является внешним относительно bot-процесса агентным runtime и расходует токены подключённой модели. Массовый auto-enqueue нельзя включать до оценки стоимости. Telegram Bot API `file_id` остаётся привязан к основному боту, поэтому отдельный storage-бот не создаётся. Первая версия не извлекает PDF, изображения, видео, RAR и TAR. Новые Telegram topics должны быть созданы владельцем, после чего их реальные thread ID задаются в `.env.server`.

## После завершения

### Фактически сделано

- добавлена migration `z031_telegram_storage_librarian.sql`;
- storage kinds расширены `inbox` и `analysis` без обязательных фиктивных thread ID;
- добавлены `telegram_storage_analysis_jobs` и `telegram_storage_analysis`;
- реализован queue claim через `FOR UPDATE SKIP LOCKED`;
- добавлена bounded загрузка multipart с SHA256 каждого part и объекта;
- реализовано безопасное чтение text, JSON, ZIP и DOCX в памяти;
- добавлено очищение credentials перед Hermes;
- реализован Hermes Runs API client через `POST /v1/runs` и `GET /v1/runs/{id}`;
- добавлены manual-first команды `/storage_librarian`, `/storage_analyze`, `/storage_digest`, `/storage_ask`;
- background scheduler запускается только при отдельном `STORAGE_LIBRARIAN_AUTO_ENQUEUE=true`;
- добавлен runbook с удалением ошибочного duplicate backup timer и production rollout;
- добавлены contract tests.

### Миграции и совместимость

Миграция заменяет check constraint допустимых storage kinds и создаёт две новые таблицы. Существующие семь kinds и Telegram objects сохраняются без изменения. Новые thread ID являются optional до создания тем и требуются только при фактической загрузке объектов kinds `inbox` или `analysis`.

### Проверки

Добавлены unit/contract tests для migration, router registration, default-disabled settings, запрета protected kinds, JSON extraction, response normalization и credential redaction. Полный CI запускается в draft PR. Production smoke-test не выполняется до merge и обновления сервера.

### PR и commit

Ветка подготовлена к draft PR в `main`. Номер PR и итоговый merge commit будут записаны после публикации и завершения CI.

### Незавершённое

- создать реальные Telegram topics `Inbox Unclassified` и `Hermes Reports`;
- записать их thread ID в production environment;
- выполнить один ручной Hermes smoke-test на небольшом diagnostics или Codex object;
- проверить стоимость и качество результата;
- решить, включать ли background auto-enqueue;
- отдельный UX ручной загрузки сообщений в Inbox и публикация digest в Hermes Reports остаются следующим срезом;
- PDF и media extraction не входят в первую версию.

### Следующий шаг

Открыть draft PR, исправить замечания CI, затем после merge обновить сервер, удалить ошибочный duplicate backup timer, проверить `/backup` и `/storage`, включить Librarian только в manual-first режиме и выполнить один `/storage_analyze ID`.
