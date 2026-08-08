# Storage Librarian stale-running recovery

- Дата: 2026-08-08
- ID: `2026-08-08-storage-librarian-stale-running-recovery`
- Линия/фаза: Storage Librarian / production lifecycle hardening
- Статус: `завершено`
- Ветка: `fix/storage-librarian-stale-running-recovery`
- Базовый commit: `45ccf8121a055631bae9b660b38254a83ef60d98`

## Перед началом

### Цель

Не допускать вечных `running` jobs после потери worker process или замены bot container во время Storage Librarian analysis.

### Production evidence

После production rollout full-archive scheduler успешно прошёл несколько циклов и создал новый completed analysis для Storage `#33`. Одновременно Storage `#30` остался `running` с `locked_at=2026-08-08 09:51:50.762508+00` и `worker_id=storage-librarian:7`.

Контроль показал, что текущий `velvet-bot-1` был создан только в `10:06:41 UTC` и запущен в `10:07:33 UTC`, то есть процесс, захвативший `#30`, уже не существовал. Сам объект `#30` состоит из одной Telegram part размером 942 bytes, поэтому длительное реальное выполнение исключалось.

### Риск

`claim_next()` переводит job в `running`, но очередь не имела lease-expiry recovery. Потеря consumer после claim могла оставить строку `running` навсегда. Такой orphan не блокировал другие jobs благодаря `SKIP LOCKED`, но сам объект больше никогда не анализировался автоматически.

## Сделано

- scheduler перед каждым циклом восстанавливает `running` jobs с lease старше 15 минут;
- orphan с оставшимися попытками возвращается в `queued`;
- orphan, уже достигший `max_attempts`, становится `failed`;
- `attempts` намеренно не сбрасывается и не уменьшается;
- `worker_id` и `locked_at` очищаются;
- recovery пишет отдельный warning только когда действительно изменил jobs;
- terminal `completed`, `failed` и `skipped` jobs не затрагиваются;
- добавлены regression tests на SQL contract и bounded stale window.

## Почему 15 минут

Production Ollama request bounded текущим `STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS` (180 seconds), Telegram part download имеет отдельный timeout, а Arthur использует тот же bounded local analysis path. Пятнадцать минут оставляют большой запас для нормальной обработки, но гарантируют автоматическое освобождение потерянного lease без ручной правки PostgreSQL.

## Миграции и совместимость

SQL migration не требуется: используются существующие поля `status`, `attempts`, `max_attempts`, `available_at`, `locked_at`, `worker_id`, `last_error`, `finished_at` и `updated_at`.

Arthur `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` не меняется. Recovery живёт только внутри уже включённого background scheduler основного Velvet bot и не создаёт второй consumer.

## Проверки

- Python syntax compile для изменённого scheduler и нового regression test;
- regression test проверяет, что attempt history не стирается;
- required GitHub CI должен пройти до merge.

## Production acceptance после merge

После штатного deploy проверить, что старый `#30` автоматически покидает `running` без ручного `UPDATE`, а в bot logs появляется `Storage Librarian stale running recovery ...` при фактическом восстановлении.
