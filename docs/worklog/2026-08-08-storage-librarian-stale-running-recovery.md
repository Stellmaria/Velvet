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

### Исходный контекст

После production rollout full-archive scheduler успешно прошёл несколько циклов и создал новый completed analysis для Storage `#33`. Одновременно Storage `#30` остался `running` с `locked_at=2026-08-08 09:51:50.762508+00` и `worker_id=storage-librarian:7`.

Контроль показал, что следующий `velvet-bot-1` был создан только в `10:06:41 UTC` и запущен в `10:07:33 UTC`, то есть процесс, захвативший `#30`, уже не существовал. Сам объект `#30` состоит из одной Telegram part размером 942 bytes, поэтому длительное реальное выполнение исключалось.

`claim_next()` переводит job в `running`, но очередь не имела lease-expiry recovery. Потеря consumer после claim могла оставить строку `running` навсегда. Такой orphan не блокировал другие jobs благодаря `SKIP LOCKED`, но сам объект больше никогда не анализировался автоматически.

### Планируемый объём

- добавить bounded recovery stale `running` jobs в существующий основной Librarian scheduler;
- сохранять `attempts` и не скрывать фактически начатые попытки;
- возвращать orphan с оставшимися попытками в `queued`;
- переводить исчерпавший попытки orphan в `failed`;
- не затрагивать terminal `completed`, `failed` и `skipped` jobs;
- покрыть recovery regression test без SQL migration.

### Критерии готовности

- `running` lease старше 15 минут автоматически освобождается;
- job с `attempts < max_attempts` снова становится доступна worker-у;
- job с `attempts >= max_attempts` не получает бесконечный retry;
- `attempts` не сбрасывается и не уменьшается;
- Arthur остаётся manual-first с `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`;
- required GitHub CI зелёный до merge.

### Риски и ограничения

Пятнадцатиминутный stale window намеренно значительно больше текущего 180-second Ollama request timeout и Telegram download timeout. Если в будущем появится легитимный единичный analysis дольше 15 минут, lease policy придётся пересмотреть вместе с end-to-end deadline.

Этот fix не решает отдельные production defects `done_reason=length` на небольших Codex ZIP и отсутствие bounded chunking для oversized diagnostics. Они остаются отдельными follow-up задачами, чтобы lifecycle recovery не превращался в архитектурный комбайн.

## После завершения

### Фактически сделано

- scheduler перед каждым циклом восстанавливает `running` jobs с lease старше 15 минут;
- orphan с оставшимися попытками возвращается в `queued`;
- orphan, уже достигший `max_attempts`, становится `failed`;
- `attempts` намеренно не сбрасывается и не уменьшается;
- `worker_id` и `locked_at` очищаются;
- recovery пишет отдельный warning только когда действительно изменил jobs;
- terminal `completed`, `failed` и `skipped` jobs не затрагиваются;
- добавлены regression tests на SQL contract и bounded stale window.

### Миграции и совместимость

SQL migration не требуется: используются существующие поля `status`, `attempts`, `max_attempts`, `available_at`, `locked_at`, `worker_id`, `last_error`, `finished_at` и `updated_at`.

Arthur `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` не меняется. Recovery живёт только внутри уже включённого background scheduler основного Velvet bot и не создаёт второй consumer.

### Проверки

- Python syntax compile для изменённого scheduler и нового regression test пройден локально;
- regression test проверяет stale predicate, queued/failed split и сохранение attempt history;
- type-check GitHub CI на первом PR head прошёл;
- после синхронизации с актуальным `main` package architecture inventory регенерирован на GitHub runner с Python 3.13 и label `p1-package-architecture-baseline`;
- полный required GitHub CI должен пройти на финальном head до merge.

### PR и commit

PR: `#731 Recover stale Storage Librarian running jobs`.

Ветка: `fix/storage-librarian-stale-running-recovery`. Финальный squash/merge SHA фиксируется после прохождения required CI и merge в `main`.

### Незавершённое

- исправить повторяющийся `done_reason=length` для небольших Codex объектов `#34`, `#35`, `#36`;
- добавить bounded chunking/summarization для oversized diagnostics вместо terminal failure всего объекта;
- после production deploy нового merge подтвердить, что исторический orphan `#30` автоматически покидает `running` без ручного `UPDATE`.

### Следующий шаг

Дождаться required CI PR #731, слить его в `main` обычным защищённым workflow, затем опубликовать и развернуть exact source/image pair и проверить production recovery на Storage `#30`.
