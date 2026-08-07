# Сессия: одноразовый production rollout Arthur Librarian Phase 2

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-production-rollout`
- Линия/фаза: Arthur Librarian Phase 2 / production rollout
- Статус: частично
- Ветка: `ops/arthur-prod-rollout-20260806`
- Базовый commit: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`
- PR: #667

## Перед началом

### Цель

Подготовить одноразовый, проверяемый и откатываемый production rollout Arthur Librarian Phase 2 через GitHub Actions без публикации секретов и без обхода канонического immutable-image deploy-контракта.

### Исходный контекст

PR #667 был создан как эксплуатационный мост для production rollout и намеренно не меняет application runtime. Ветка изначально была привязана к commit `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f` и к заранее опубликованному immutable image digest.

После создания PR в `main` были объединены #666 и #662, а #663 находится в подготовке. Поэтому исходный `SOURCE_COMMIT` и image digest в rollout workflow уже считаются устаревшими и не должны использоваться для production. Финальный provenance обязан быть обновлён только после merge всех предшествующих application PR и успешного штатного `publish-image.yml` для точного нового `main`.

### Планируемый объём

- синхронизировать rollout-ветку с актуальным `main` после завершения зависимых PR;
- получить immutable image digest только из успешного штатного publish pipeline для точного production source commit;
- обновить `SOURCE_COMMIT` и `IMAGE_DIGEST` в one-time workflow;
- сохранить отдельную установку Arthur production credentials без вывода значений;
- использовать канонический `deploy/server/deploy.sh`, а не отдельный альтернативный deploy path;
- после deploy выполнить fixed-target Librarian reconcile и эксплуатационные health checks;
- проверить отсутствие published ports, heartbeat, manual-only queue mode, Ollama model availability и Telegram `getMe`;
- не запускать production rollout до отдельного явного решения на merge PR #667.

### Критерии готовности

- rollout source commit совпадает с проверенным актуальным `main`;
- image digest получен из успешного `publish-image.yml` для этого же source commit;
- required GitHub checks PR #667 зелёные;
- workflow не печатает production credentials или токены;
- rollout script сохраняет immutable deploy и fixed-target reconcile contracts;
- merge PR #667 остаётся единственной точкой запуска одноразового production rollout;
- до merge пользователю явно сообщено, что merge запускает production.

### Риски и ограничения

- merge этого PR является эксплуатационным действием и запускает production rollout, поэтому он не должен выполняться автоматически как обычная уборка PR;
- использование старого source commit вместе с новым checkout создаёт риск несовместимого production состояния;
- digest должен быть связан с точным source commit, а не с плавающим tag;
- production credentials разрешено только передавать через GitHub environment/secrets и серверные файлы с ограниченными правами, без вывода значений;
- live Telegram, Ollama и Librarian проверки доступны только во время фактического rollout.

## После завершения

### Фактически сделано

Подготовлен one-time workflow `.github/workflows/arthur-production-rollout-v2.yml` и серверный bridge `.github/ops/arthur-production-rollout.sh`. Контракт предусматривает immutable application deploy, отдельную установку Arthur credentials, восстановление checkout на итоговый merge commit, fixed-target Librarian reconcile и post-deploy health checks.

На текущем этапе rollout не запускался. Обнаружено, что исходные provenance-значения PR устарели после движения `main`; они намеренно не заменяются промежуточным образом после #662, потому что #663 ещё должен завершить protected CI и, после merge, пройти штатный image publish. Таким образом исключается deployment заведомо промежуточного состояния.

### Миграции и совместимость

SQL-миграций в PR нет. Application runtime PR напрямую не меняет. Совместимость зависит от строгого совпадения final `SOURCE_COMMIT` и immutable image digest, опубликованного для этого commit штатным pipeline.

### Проверки

Проверена структура rollout workflow и server bridge: deployment идёт через существующий канонический deploy script, secret values не должны печататься, предусмотрены container health, no-published-ports, queue mode, Ollama, heartbeat и Telegram identity checks.

Финальный protected CI, точный provenance и production live-smoke ещё не заявляются выполненными. Они должны быть выполнены после синхронизации ветки с итоговым `main` и обновления verified image digest.

### PR и commit

- PR: #667 `Ops: one-time Arthur production rollout`.
- Ветка: `ops/arthur-prod-rollout-20260806`.
- Исходный базовый commit: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`.
- Финальный rollout source commit и image digest будут зафиксированы отдельной правкой после завершения зависимых application PR.

### Незавершённое

- дождаться полного зелёного protected CI и merge PR #663;
- дождаться успешного `publish-image.yml` для точного merge commit нового `main`;
- получить published immutable digest из артефакта pipeline;
- синхронизировать #667 с актуальным `main`;
- обновить rollout provenance и формулировки PR;
- прогнать required checks #667;
- остановиться перед merge, поскольку merge запускает production rollout;
- после отдельного решения на rollout проверить фактический production result.

### Следующий шаг

Завершить #663, получить verified immutable image для нового `main`, затем обновить #667 до точного source/digest pair и довести его required CI до зелёного состояния без запуска production.
