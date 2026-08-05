# Сессия: canonical media provider adapters

- Дата: 2026-08-05
- ID: 2026-08-05-canonical-media-provider-adapters
- Линия/фаза: P1 provider architecture, issue #459
- Статус: частично
- Ветка: fix/459-canonical-provider-adapters
- Базовый commit: a3c16498b4d92521719881bccc3ea132644f83fd

## Перед началом

### Цель

Заменить order-dependent provider monkeypatch graph явными Kie/GRS adapters,
registry, route contract и обычной retry policy, сохранив billing safety,
provider-specific semantics и текущие пользовательские сценарии.

### Исходный контекст

В актуальном `main` provider behavior собирался через `importlib`, assignment
чужих methods/classes и несколько startup installers. GRS status normalization,
violation retry, balance fallback, worker speedups и Vision fallback зависели от
порядка установки. Live provider payload и credit acceptance отдельно
отслеживаются issue #412 и не входят в repository-only приёмку #459.

### Планируемый объём

- ввести typed `MediaProviderAdapter`, provider routes и registry;
- реализовать явные Kie/GRS adapters;
- перенести GRS moderation, image guard, balance fallback и retry в обычный код;
- создавать активный friendly/economy worker напрямую;
- сделать Vision fallback явным вызовом без replacement methods;
- удалить obsolete GRS installers и их architecture exemptions;
- добавить regression tests и пересобрать canonical inventories.

### Критерии готовности

- provider/model routing выбирается через стабильный contract;
- Kie и GRS submit/status/balance paths тестируются без startup monkeypatch;
- unknown-submit остаётся fail-closed;
- unsupported cancellation не выполняет network side effects;
- obsolete provider installers отсутствуют в startup graph;
- focused и полный required CI проходят на exact PR head;
- PR #639 слит в `main`, issue #459 закрыта.

### Риски и ограничения

- реальный provider API не вызывается из CI;
- live payload, credit и latency acceptance остаётся #412;
- SQL migration и production rollout не входят в задачу;
- изменение retry semantics могло затронуть billing safety, поэтому сохранены
  sequential paid-attempt persistence и terminal/transient classification.

## После завершения

### Фактически сделано

- добавлен typed `MediaProviderAdapter` contract и registry;
- Kie и GRS направлены через explicit adapters по stable model aliases;
- GRS violation parsing, image-only guard, balance fallback и retry policy
  перенесены в normal domain/infrastructure code;
- canonical friendly/economy worker создаётся напрямую вместо replacement
  `app.workers.KieGenerationWorker` при startup;
- Vision model fallback вызывается из `VisionClient`, без assignment его
  `__init__` и `_read_json`;
- удалены GRS resilience, campaign, speedup и branding installer modules;
- provider identity для usage/delivery берётся из model contract;
- Telegram progress resilience отвязана от retired GRS installer modules;
- owner privacy/progress policy подключена к canonical worker boundary;
- временный sanitizer facade удалён, функция размещена в существующем
  formatting boundary;
- Ollama discovery ловит только `VisionAnalysisError`, без нового broad
  exception boundary;
- пересобраны canonical architecture, repository и package inventories;
- exemption fingerprints обновлены штатным `--bootstrap-exemptions`, без
  расширения зарегистрированного architecture debt.

### Миграции и совместимость

SQL migrations отсутствуют. Callback payloads, stored task records и public UI
contracts не меняются. Unsupported provider cancellation явно возвращает
`False`. Production services, secrets и provider credentials не изменялись.

### Проверки

Implementation commit `14af196a3258e74bafb783a61d7671223856e36b`
прошёл в GitHub Actions run `30991264086`.

Finalizer job `92268618850` в run `30994195410` успешно проверил и опубликовал
clean implementation head `c3156bf2632ab6a34ac1302a6faae25007451a88`:

- `python -m compileall -q main.py velvet_bot scripts tests`;
- `git diff --check`;
- canonical architecture, repository, shared-contract и navigation inventories;
- 55 focused provider, worker, privacy, routing, composition и architecture tests;
- удаление временного workflow и sanitizer facade.

После full-CI findings дополнительно:

- retired installer assertions перенесены на canonical composition stages;
- P2 stability inventory возвращён к 106 broad exceptions и 0 unresolved через
  конкретный `VisionAnalysisError` catch;
- repository layout generator и три P3E tests прошли в run `30998011031`;
- clean canonical repository commit: `90f9760e36cceae098357662c77de1d2122a1640`;
- package architecture inventory, exemption ledger и canonical `--check`
  прошли в run `30998513778`;
- clean canonical package commit: `a439fcc43259bdfc586a4115a95c18494395fd19`.

Полный required CI выполняется на следующем exact PR head перед merge. Отдельный
API commit используется только для штатного запуска workflow после commit,
созданного `GITHUB_TOKEN`.

### PR и commit

- PR: #639 `Canonicalize media provider adapters and retry policy`;
- implementation commit: `14af196a3258e74bafb783a61d7671223856e36b`;
- canonical retirement commit: `c3156bf2632ab6a34ac1302a6faae25007451a88`;
- canonical repository commit: `90f9760e36cceae098357662c77de1d2122a1640`;
- canonical package commit: `a439fcc43259bdfc586a4115a95c18494395fd19`;
- final merge commit: ожидается после required CI.

### Незавершённое

- дождаться всех required checks на exact PR head;
- устранить возможные CI/review findings;
- выполнить squash merge PR #639;
- убедиться, что issue #459 закрыта автоматически.

### Следующий шаг

Проверить exact-head required CI, затем слить PR #639 в `main` без production
rollout. Live provider acceptance продолжить отдельно в #412.
