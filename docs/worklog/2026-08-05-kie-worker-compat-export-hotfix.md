# Сессия: Kie worker compatibility export hotfix

- Дата: 2026-08-05
- ID: 2026-08-05-kie-worker-compat-export-hotfix
- Линия/фаза: production hotfix / стабилизация Ауф runtime
- Статус: частично
- Ветка: `fix/kie-worker-compat-export`
- Базовый commit: `60b38f986297f1ecd544accc9e7d1e56c8f733b3`

## Перед началом

### Цель

Восстановить production startup после provider-worker canonicalization, сохранив
активный `FriendlyKieGenerationWorker` и прежний публичный bootstrap contract
`velvet_bot.app.workers.KieGenerationWorker` для переходных installers.

### Исходный контекст

Production deploy commit `60b38f986297f1ecd544accc9e7d1e56c8f733b3`
прошёл preflight, verified dump restore и image build, но bot стал unhealthy при
`install_auf_generation_receipts()`: модуль `velvet_bot.app.workers` больше не
экспортировал `KieGenerationWorker`. Штатный deploy откатил checkout и bot image
на `74bfb3a19506e5b2a387f4de62b711808ea88a4c`; rollback health и server smoke
прошли, база автоматически не восстанавливалась.

Регрессия возникла после перехода на прямое создание
`FriendlyKieGenerationWorker`: активный класс был заменён корректно, но
переходное экспортное имя продолжали использовать receipt и runtime installers.
Существующий composition test проверял только порядок stage names и не выполнял
installer contract.

### Планируемый объём

- экспортировать canonical friendly worker под совместимым именем
  `KieGenerationWorker` в `velvet_bot.app.workers`;
- использовать то же имя при создании worker instances;
- добавить regression test публичного export contract и executable receipt
  installer boundary;
- выполнить focused tests и required CI;
- слить hotfix только после exact-head checks;
- повторить штатный production deploy и live smoke отдельно после merge.

### Критерии готовности

- `velvet_bot.app.workers.KieGenerationWorker` существует и является
  `FriendlyKieGenerationWorker`;
- receipt installer способен установить delivery handler без `AttributeError`;
- runtime dispatcher получает тот же canonical worker class;
- focused tests и required CI проходят;
- production rollout остаётся отдельной живой проверкой и не объявляется
  завершённым до повторного deploy.

### Риски и ограничения

- SQL migrations отсутствуют;
- provider API и платные генерации не вызываются;
- сохраняется переходный installer contract до cleanup issue #455/#457;
- module alias не должен возвращать retired economy worker в production;
- серверные secrets и database state не меняются этим PR.

### Ответы режима стабилизации

1. Улучшается существующий startup Ауф и media generation workers.
2. Production deploy снова сможет завершить composition bootstrap без crash loop.
3. Новая предметная область не добавляется; восстанавливается прежний contract.
4. Улучшение проверяется import/installer regression tests, CI и повторным deploy.
5. Canonical friendly worker, durable delivery и provider adapter boundaries
   сохраняются.

## После завершения

### Фактически сделано

- `velvet_bot.app.workers.KieGenerationWorker` восстановлен как публичное имя
  canonical `FriendlyKieGenerationWorker`;
- обычная регистрация Kie workers использует то же экспортное имя, поэтому
  receipt installer, runtime dispatcher и фактически создаваемые workers больше
  не расходятся по class contract;
- добавлен regression test, который проверяет точную identity export-а и наличие
  `install_delivery_handler`;
- добавлен isolated subprocess smoke, выполняющий все feature installers в
  объявленном порядке вместо прежней проверки только списка stage names;
- package architecture inventory пересобран штатным генератором на Python 3.13;
- hard-coded package LOC baseline синхронизирован с generated inventory;
- временный branch-only workflow генерации удалён из итогового diff.

### Изменённые модули и контракты

- `velvet_bot/app/workers.py`: compatibility export canonical friendly worker;
- `tests/test_kie_worker_bootstrap_contract.py`: executable startup regression;
- `tests/test_package_architecture_inventory.py`: generated LOC baseline;
- `docs/package_architecture_inventory.json` и `.md`: deterministic import
  fingerprint после изменения public alias;
- этот worklog: incident, rollback, implementation и validation evidence.

### Миграции и совместимость

SQL migrations отсутствуют. Compatibility export сохраняет существующих
потребителей `app.workers.KieGenerationWorker`, не меняя stored data, provider
routing, durable delivery ownership или public Telegram payloads. Retired economy
worker не возвращается в production construction.

### Проверки

Production incident evidence:

- preflight: PASS;
- pre-deploy custom dump restore: PASS, `migrations=92`, `tables=105`,
  `characters=96`;
- новый bot startup: FAIL до worker manager с `AttributeError` на отсутствующем
  `app.workers.KieGenerationWorker`;
- automatic code/image rollback: PASS;
- rollback bot health: PASS;
- rollback server smoke: PASS, `active_ai_tasks=0`, Telegram intentionally
  skipped;
- database rollback не выполнялся;
- verified dump сохранён как
  `/srv/velvet/data/backups/predeploy-20260805T204320Z-74bfb3a19506.dump`.

Initial CI head `ad5cb18d5f10db0b2db503c3ac567d452565c10a`, run
`31046201183`:

- Python compile: PASS;
- PostgreSQL test shards 0, 1, 2 и 3: PASS;
- новый Kie bootstrap installer smoke: PASS в полном shard;
- preflight выявил только stale package architecture inventory;
- project notes run `31046201141`: PASS;
- type check run `31046201262`: PASS.

Inventory synchronization workflow run `31046368385`: PASS. Генератор выполнил
`--write`, затем `--check`; временный workflow удалён.

Exact functional head `55c23bf6197f4189f798985b0337863ba0d09fb3`:

- tests run `31046892337`: preflight PASS, PostgreSQL shards 0/1/2/3 PASS,
  aggregate `unit-tests` PASS;
- security run `31046892859`: static security PASS, CodeQL Actions PASS,
  CodeQL Python PASS, image vulnerability gate/SBOM/provenance PASS,
  supply-chain contract PASS;
- Docker build run `31046892220`: PASS;
- type check run `31046891543`: PASS;
- project notes run `31046892976`: PASS;
- branch protection run `31046891564`: branch protection and Docker build
  contract PASS.

После этой записи запускается финальный exact-head CI только с дополнительным
worklog evidence; merge разрешён лишь после его завершения.

### PR и commit

- PR: #647 `Restore canonical Kie worker bootstrap export`;
- worklog start: `45717ae1a2f578205d41f834eb015720dd6a5b60`;
- compatibility export: `9fe01c5af72f8080a1b34f22b48af041bee471e3`;
- regression tests: `ad5cb18d5f10db0b2db503c3ac567d452565c10a`;
- deterministic inventory: `14e08a43c7e5bdcf97bfec26e3653b3607503e65`;
- temporary workflow removal: `3b1e5d4f66d8fa623ae466deece2df246d333e28`;
- validation evidence: `31dee84867213eb595fe1181c34a4b7ccd934f10`;
- LOC baseline sync: `55c23bf6197f4189f798985b0337863ba0d09fb3`;
- final merge commit: ожидается после final exact-head CI.

### Незавершённое

- пройти финальный required CI после записи validation evidence;
- слить PR #647;
- повторить production deploy и server smoke;
- после успешного rollout продолжить live acceptance AI queue по #603.

### Следующий шаг

Проверить final exact-head required CI, слить PR #647 и повторить pinned
production deploy через штатный rollback-capable script.
