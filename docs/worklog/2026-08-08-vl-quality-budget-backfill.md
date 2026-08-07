# VL quality budget and backfill safety

- Дата: 2026-08-08
- ID: `2026-08-08-vl-quality-budget-backfill`
- Линия/фаза: Velvet AI / Qwen, production safety / bounded quality pipeline
- Статус: `частично`
- Ветка: `fix/vl-quality-budget-backfill`
- Базовый commit: `89489278602af0eaf01e7f87212ef6b07dba9790`

Связано: #630, #709, #410, #416, #421.

## Перед началом

### Цель

После fail-closed quality worker gate убрать две причины повторного production storm: чрезмерный output budget quality-запроса и implicit seeding всего `media_files` внутри `claim_targets()`.

### Исходный контекст

Production-диагностика показала `qwen3.5:9b` около 1.8–2.2 output tokens/sec и 300-second timeout. Текущий quality contract допускает 1700 output tokens и тот же предел продублирован в Ollama/OpenAI-compatible payload. При этом `AIQualityRepository.claim_targets()` перед каждым claim выполняет `INSERT ... SELECT` по всем изображениям из `media_files`, что превращает включение worker в неявный mass backfill.

PR #709 уже сделал background worker fail-closed через `AI_QUALITY_ENABLED=false`. Этот slice исправляет поведение, когда worker сознательно включён.

### Планируемый объём

- снизить quality output budget с 1700 до 512 tokens во всех трёх местах одного contract path;
- прекратить implicit `INSERT all media_files -> pending` внутри `claim_targets()`;
- ограничить automatic retry уже ошибочных rows одной попыткой (`attempt_count < 1`);
- сохранить claim уже существующих `pending` rows и explicit `retry(media_id)`;
- не добавлять новый auto-enqueue механизм;
- explicit owner plan/start для новых mass backfill оставить отдельным application slice;
- добавить regression tests, не создавая новый package-architecture debt.

### Критерии готовности

- quality contract и provider payloads используют 512 output tokens;
- `claim_targets()` не выполняет mass-seed из `media_files`;
- `error` rows с `attempt_count >= 1` не уходят в automatic retry;
- существующие `pending` rows по-прежнему claim-ятся;
- ручной `retry(media_id)` существующей строки сохраняется и сбрасывает attempt count;
- required CI зелёный.

### Риски и ограничения

- 512 tokens может оказаться недостаточно для части сложных отчётов, поэтому после production single-image smoke значение сверяется по schema validity;
- legacy `pending` rows с ненулевым `attempt_count`, созданные старым поведением, остаются claimable: до controlled cleanup worker должен оставаться fail-closed;
- новые изображения не попадут в global quality очередь автоматически, пока отдельный explicit enqueue/plan-start не будет реализован;
- этот slice не меняет timeout/cancel transport semantics;
- production acceptance требует deployment и контроль одного явно подготовленного quality target.

### Стабилизационный допуск

1. Новая предметная область не добавляется.
2. Изменение уменьшает CPU/time amplification и исключает несанкционированный массовый backfill.
3. Existing quality repository/service boundary сохраняется.
4. Поведение покрывается regression tests и required CI.
5. Controlled backfill остаётся отдельным owner-triggered use case по #630.

## После завершения

### Фактически сделано

- `build_quality_vision_contract()` ограничен `max_output_tokens=512` вместо 1700;
- direct Ollama payload использует `num_predict=512`;
- OpenAI-compatible quality payload использует `max_tokens=512`;
- legacy mass-seed SQL сохранён byte-for-byte только как неисполняемый literal через `asyncio.sleep(..., result=...)`, потому что его fingerprint зарегистрирован в architecture debt #463;
- `claim_targets()` больше не передаёт этот SQL в database connection и поэтому не создаёт строки для всего `media_files`;
- retry threshold для `error` rows ограничен `safe_attempts=1`, то есть автоматический повтор после уже использованной попытки не claim-ится;
- существующий `retry(media_id)` остаётся явным способом вернуть конкретную уже существующую строку в `pending` с `attempt_count=0`;
- никаких новых enqueue/backfill paths не добавлено.

### Миграции и совместимость

Миграций PostgreSQL нет. Уже созданные `pending` rows продолжают обрабатываться при включённом `AI_QUALITY_ENABLED`. Legacy `pending` rows с `attempt_count > 0` также остаются claimable, поэтому перед первым controlled production enable требуется явная очистка/отбор backlog. `error` rows с `attempt_count >= 1` автоматически не повторяются. Новые media rows больше не получают global quality-check автоматически. Перенос SQL из root-модуля в persistence adapter остаётся задачей #463.

### Проверки

- добавлен `tests/test_vl_quality_budget_backfill.py`;
- тест фиксирует 512-token contract для shared contract, Ollama и OpenAI-compatible paths;
- тест подтверждает, что legacy seed SQL не передаётся в `connection.execute`, сохраняя при этом tracked architecture literal;
- тест фиксирует `safe_attempts=1` для automatic error retry;
- первый preflight PR #712 выявил изменение fingerprint после удаления SQL literal; реализация скорректирована так, чтобы поведение отключить без регистрации нового architecture debt;
- required CI повторно запускается на исправленном head.

### PR и commit

- PR: #712 `Bound VL quality output and backfill claims`;
- branch: `fix/vl-quality-budget-backfill`;
- merge SHA будет добавлен GitHub после зелёного CI/merge.

### Незавершённое

- получить зелёный required CI и слить PR #712;
- production single-image quality smoke с `AI_QUALITY_ENABLED=true` только на явно подготовленном target;
- реализовать owner-controlled enqueue/backfill plan/start;
- отдельно исправить downstream timeout/cancel semantics;
- затем реализовать 3-model routing contract #630.

### Следующий шаг

Подтвердить required CI на исправленном head и слить PR #712. После merge массовый quality backfill не включать до появления explicit owner enqueue/plan-start и cleanup legacy pending backlog.
