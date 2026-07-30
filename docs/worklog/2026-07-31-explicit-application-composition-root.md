# 2026-07-31 — Explicit application composition root

- Дата: 2026-07-31
- ID: `explicit-application-composition-root`
- Issue: #455
- Линия/фаза: P0 correctness-risk architecture
- Статус: `частично`
- Ветка: `agent/p0-explicit-application-composition`
- Базовый commit: `2cb9a96ec5ce5066436c83323279855047cb67a7`

## Перед началом

### Цель

Убрать неявную package-level точку входа через `velvet_bot.app.__getattr__` и выразить текущий startup order typed composition contract, не меняя фактическое поведение 27 runtime installation stages.

### Исходный контекст

`velvet_bot/app/__init__.py` одновременно был package facade, lazy bootstrap и местом исполнения всех application-wide installers. Доступ к `run_application` запускал side effects через `__getattr__`, после чего nested function импортировала и выполняла ещё 25 feature stages. Фактическая реализация зависела от import order и не была доступна как typed object. Package-wide baseline #460 уже фиксировал 27 стадий, но не предоставлял явной composition boundary для их последовательного удаления по #455.

### Планируемый объём

- добавить `CompositionStage` и `ApplicationComposition`;
- разделить bootstrap stages и feature stages;
- сохранить точный порядок всех 27 текущих installers;
- сохранить lazy imports, чтобы runtime stability и datetime compatibility выполнялись до импорта bootstrap;
- экспортировать обычную `run_application` из `velvet_bot.app`;
- блокировать расхождение declared и actual feature-stage order;
- добавить regression tests порядка, phase boundary и explicit package export;
- пересчитать package-wide architecture inventory exact-head workflow.

### Критерии готовности

- `velvet_bot.app` экспортирует обычную `run_application` без `__getattr__`;
- default composition содержит все 27 текущих stages в прежнем порядке;
- bootstrap runner импортируется только после двух bootstrap stages;
- feature installer modules импортируются только после bootstrap runner;
- расхождение declared и actual stage order завершается явной ошибкой;
- package inventory и exemptions соответствуют новому source layout;
- unit tests, type check, Docker build и project notes contract проходят.

### Риски и ограничения

Этот срез не удаляет сами installers, `_INSTALLED` sentinels и foreign assignments. Он намеренно не меняет provider routing, charging, delivery, Telegram UI и worker behavior. Изменение import timing ограничено сохранением прежней boundary: bootstrap stages выполняются до импорта `velvet_bot.app.bootstrap`, а feature modules загружаются после него. Delivery recovery и hotfix layers остаются до #457, provider layers до #459, Ауф application/presentation migration до #458.

## После завершения

### Фактически сделано

- добавлен `velvet_bot/app/composition.py` с typed startup model;
- bootstrap phases выполняются до загрузки `velvet_bot.app.bootstrap.run_application`;
- feature installer modules загружаются только после bootstrap phases и runner import;
- `velvet_bot/app/__init__.py` стал обычным explicit export без `__getattr__` и package import side effects;
- default composition перечисляет все 27 stages и делает порядок читаемым без анализа import history;
- runtime guard блокирует расхождение declared и actual feature stage order;
- добавлены unit tests полного order contract, phase boundary, drift guard и package export;
- exact-head workflow пересчитал generated package inventory/exemptions и удалил себя в generated commit `d37df56ea4fc1aa7f10333563bd250e56d652f0b`.

### Миграции и совместимость

Миграций базы данных нет. Callback payload, FSM state, provider model ids, charging, task lifecycle и пользовательские тексты не изменены. Installer implementations и их relative order сохранены. Новый composition contract пока оборачивает legacy stages и служит явной точкой последующего burn-down, а не объявляет текущие patches целевой архитектурой.

### Проверки

- `tests/test_application_composition.py`;
- полный unit test suite;
- `python scripts/inventory_package_architecture.py --check --label p1-package-architecture-baseline`;
- bounded type check;
- Docker build;
- project notes contract;
- mergeability PR и отсутствие unresolved review threads.

### PR и commit

- Issue: #455;
- PR: #483;
- ветка: `agent/p0-explicit-application-composition`;
- базовый commit: `2cb9a96ec5ce5066436c83323279855047cb67a7`;
- generated package baseline: `d37df56ea4fc1aa7f10333563bd250e56d652f0b`;
- итоговый squash merge commit фиксируется GitHub после зелёного CI.

### Незавершённое

- 25 feature installers и два bootstrap installers остаются runtime side-effect stages;
- foreign assignments и `_INSTALLED` process globals не удалены;
- worker/provider/delivery/UI implementations ещё не передаются через factories;
- startup rollback для partially installed legacy stages не реализован;
- #455 остаётся открытой до полного удаления installer chain и повторяемого explicit startup.

### Следующий шаг

Перенести первую изолированную family, не меняющую provider/delivery behavior, из side-effect installer в explicit registration. Предпочтительный следующий bounded slice: infrastructure/model routing либо isolated worker registration. Delivery recovery/hotfix layers сохраняются до канонического pipeline #457.
