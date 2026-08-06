# Error Incident write amplification (#605)

- Дата: 2026-08-06
- ID: #605
- Линия/фаза: P1 production performance / Error Incident Center
- Статус: `частично`
- Ветка: `feat/issue-605-error-incident-batching-v2`
- Базовый commit: `dc14c0c5087244e37394655c12aeb0208afa50c8`

## Перед началом

### Цель

Снизить write amplification Error Incident Center при массовом повторении одного fingerprint, сохранив немедленную регистрацию новых инцидентов и `CRITICAL`, корректные acknowledge/reopen semantics и bounded использование памяти.

### Исходный контекст

Каждый повтор одного fingerprint выполнял отдельную транзакцию `SELECT ... FOR UPDATE` + `UPDATE`, а затем инициировал обновление Telegram-сообщения. Во время error storm диагностическая подсистема тем самым усиливала нагрузку на PostgreSQL и Telegram именно в момент деградации.

### Планируемый объём

- добавить bounded aggregation повторов по fingerprint;
- сохранять первый occurrence и `CRITICAL` немедленно;
- выполнять atomic PostgreSQL batch update `occurrence_count += N`;
- не переписывать `summary` и `details` при batch update;
- не допускать понижения severity;
- обеспечить flush по интервалу, pressure limit и graceful shutdown;
- сохранить acknowledge/reopen semantics;
- сократить Telegram edits до одного на batch;
- добавить наблюдаемые counters и regression tests;
- пересчитать generated architecture inventories.

### Критерии готовности

- первый occurrence регистрируется без ожидания batch window;
- тысяча одинаковых повторов агрегируется в одну batch write;
- `CRITICAL` и escalation до `CRITICAL` проходят немедленно;
- severity монотонна в immediate и batch paths;
- неудачный flush не теряет pending count и допускает повтор;
- acknowledge выполняется после flush, следующий occurrence корректно reopen-ит incident;
- shutdown делает final flush;
- память имеет явные пределы;
- focused tests и обязательный CI проходят;
- production acceptance отделён от implementation slice и не подменяется предположениями.

### Риски и ограничения

В текущей сессии нет доступа к VPS и PostgreSQL runtime metrics. Поэтому невозможно честно выполнить synthetic production storm и сравнить `pg_stat_statements`, WAL/IO, latency и Telegram rate. Graceful shutdown flush-ит pending batches, но принудительное завершение процесса без shutdown может потерять события внутри текущего двухсекундного окна; это осознанный компромисс между write amplification и durability повторов, при этом первый occurrence всегда уже сохранён.

## После завершения

### Фактически сделано

- первый fingerprint и все `CRITICAL` сохраняются и публикуются немедленно;
- известные `WARNING`/`ERROR` агрегируются в памяти по fingerprint;
- flush выполняется каждые 2 секунды, при достижении pending limit и при graceful shutdown;
- batch использует один atomic PostgreSQL update `occurrence_count += N`;
- batch update не переписывает `summary` и `details`;
- immediate и batch paths сохраняют максимальную severity;
- escalation до `CRITICAL` обходит digest cooldown;
- acknowledge сначала flush-ит pending counts и сбрасывает known cache;
- неудачный flush возвращает batch в память и учитывается в metrics;
- память ограничена queue `1000`, pending fingerprints `500`, known fingerprints `2000`;
- Telegram message edit выполняется один раз на batch;
- `ErrorIncidentCenter.aggregation_metrics()` сообщает received, new groups, aggregated repeats, flush batches, rows updated, suppressions, flush errors, dropped events, pending count и oldest pending age;
- generated package/shared-contract inventories пересчитаны поверх актуальной базы;
- canonical architecture slice синхронизирован в `development_status.md`, `project_memory.md` и `ARCHITECTURE_AUDIT.md`;
- новые broad-catch boundaries зарегистрированы с точными причинами: сохранение immediate `CRITICAL`, pressure fallback и возврат failed batch в pending;
- `docs/p2_stability_inventory.json` и `.md` пересчитаны каноническим генератором.

### Миграции и совместимость

Миграция схемы не требуется. Существующая таблица `error_incidents` и публичные интерфейсы сохраняются. Изменяется только стратегия записи повторов и частота Telegram updates. Первый occurrence, acknowledge и reopen остаются совместимыми с прежним поведением.

### Проверки

Добавлены regression tests для:

- 1000 одинаковых повторов с одной batch write;
- немедленного `CRITICAL` escalation;
- retry без потери pending count после ошибки flush;
- корректного acknowledge/reopen;
- final flush при shutdown;
- monotonic immediate severity;
- atomic batch SQL без rewrite payload.

Точечная Python compilation прошла. Generated package/shared-contract inventories пересчитаны каноническим Python 3.13; `scripts/ci_preflight.py` прошёл до фиксации итогового inventory commit. Canonical docs sync test и `git diff --check` прошли на commit `46423a1ab20a5ba4454d4591b84a15b394685cc5`. P2 stability regeneration на commit `89888d581c3efb392b3b179e3123ca736c47f414` прошёл `tests.test_p2_stability_inventory`, `tests.test_p2l_discussion_middleware_boundary`, `tests.test_error_incident_aggregation` и `git diff --check`. Полный обязательный CI повторно запускается на финальном пользовательском commit.

### PR и commit

- PR: #661
- База PR: `dc14c0c5087244e37394655c12aeb0208afa50c8`
- Канонический inventory commit: `802a12564bcb89b5a71cf2c25383cc5f2abf2814`
- Canonical docs commit: `46423a1ab20a5ba4454d4591b84a15b394685cc5`
- P2 stability inventory commit: `89888d581c3efb392b3b179e3123ca736c47f414`
- Итоговый merge commit определяется после обязательного CI.

### Незавершённое

Не выполнено production acceptance из Definition of Done: synthetic storm на VPS или production-like окружении, сравнение `pg_stat_statements`, WAL/IO, latency и Telegram notification rate. Issue #605 остаётся открытым после merge implementation slice.

### Следующий шаг

Дождаться зелёного обязательного CI и слить PR #661 в `main`. После восстановления доступа к VPS провести production storm acceptance, приложить измерения к #605 и только затем решать вопрос о закрытии issue.
