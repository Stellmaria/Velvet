# Error Incident write amplification (#605)

## Статус

Implementation slice готовится в ветке `feat/issue-605-error-incident-batching`. Production acceptance остаётся отдельным шагом, поскольку в текущей сессии нет доступа к VPS и PostgreSQL runtime metrics.

## Проблема

Повтор одного fingerprint обрабатывался как отдельная транзакция `SELECT ... FOR UPDATE` + `UPDATE`, после чего для каждого события выполнялась попытка обновить Telegram-сообщение. Error storm тем самым создавал собственную нагрузку на PostgreSQL и Telegram именно в момент деградации системы.

## Решение

- первый fingerprint сохраняется и публикуется немедленно;
- известные `WARNING`/`ERROR` агрегируются в памяти по fingerprint;
- flush выполняется каждые 2 секунды, при достижении bounded map limit и при graceful shutdown;
- batch использует один atomic PostgreSQL update `occurrence_count += N`;
- `summary` и `details` на повторном batch update не переписываются;
- severity не понижается;
- `CRITICAL` и escalation до `CRITICAL` не ждут batch window;
- acknowledge сначала flush-ит pending counts, затем фиксирует acknowledgement;
- неудачный flush возвращает batch в память и учитывается в metrics;
- память ограничена queue `1000`, pending fingerprints `500`, known fingerprints `2000`;
- Telegram message edit выполняется один раз на batch вместо одного раза на occurrence.

## Метрики

`ErrorIncidentCenter.aggregation_metrics()` возвращает:

- received events;
- new incident groups;
- aggregated repeats;
- flush batches;
- rows updated;
- notification suppressions;
- flush errors;
- dropped queue events;
- pending fingerprint count;
- oldest pending age.

## Проверки

Добавлены regression tests для:

- 1000 одинаковых повторов с одной batch write;
- немедленного `CRITICAL` escalation;
- retry без потери pending count после ошибки flush;
- корректного acknowledge/reopen;
- final flush при shutdown;
- atomic SQL contract без rewrite payload.

## Production acceptance

После появления доступа к VPS требуется synthetic storm на staging/production-like окружении и сравнение `pg_stat_statements`, WAL/IO, Telegram rate и latency до/после. Issue #605 не должен закрываться до фиксации этих evidence.
