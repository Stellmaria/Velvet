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

Ожидается после реализации и проверок.

### Изменённые модули и контракты

Ожидается после реализации и проверок.

### Миграции и совместимость

SQL migrations отсутствуют. Compatibility export сохраняет существующих
потребителей `app.workers.KieGenerationWorker`, не меняя stored data или public
Telegram payloads.

### Проверки

Ожидается после реализации и CI.

### PR и commit

Ожидается после публикации PR.

### Незавершённое

- реализовать hotfix и regression tests;
- пройти exact-head required CI;
- слить PR;
- повторить production deploy и server acceptance.

### Следующий шаг

Восстановить worker export contract, затем выполнить focused tests.
