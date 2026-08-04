# Сессия: защита terminal status Hermes coder

- Дата: `2026-08-04`
- ID: `hermes-terminal-status-guard-20260804`
- Линия/фаза: `server operations / Hermes coder runtime reliability`
- Статус: `частично`
- Ветка: `fix/hermes-terminal-status-guard`
- Базовый commit: `e2eef3ec61147259ead1848cb7d6f21834d3ce66`
- Issue: `#592`

## Перед началом

### Цель

Не допустить перезаписи уже terminal run (`completed`, `failed`, `cancelled`)
состоянием `failed`, если подготовка disposable workspace завершается ошибкой
или если cancellation происходит одновременно с clone/fetch preparation.

### Исходный контекст

- direct remote partial clone, fail-closed workspace preparation и `init: true`
  для coder-контейнеров уже находятся в `main`;
- поведенческая проверка обнаружила оставшуюся гонку: run, уже переведённый в
  `cancelled`, мог быть перезаписан как `failed` обработчиком preparation error;
- `_execute()` записывал `workspace_preparation_started` до проверки terminal
  состояния;
- `_record_workspace_preparation_failure()` безусловно записывал terminal
  `failed`;
- отдельный nested bubblewrap smoke defect не относится к этому изменению.

### Планируемый объём

- определить единый набор terminal run statuses;
- завершать `_execute()` до workspace preparation для уже terminal run;
- не записывать preparation failure поверх terminal run;
- добавить regression-тесты для `completed`, `failed`, `cancelled`;
- добавить тест cancellation во время `_prepare_workspace()`;
- не менять compose, systemd, AppArmor, migrations и production runtime.

### Критерии готовности

- existing terminal `status`, `finished_at` и `last_event` сохраняются;
- `_prepare_workspace()` и parent runner не вызываются для terminal run;
- cancellation, возникшая во время preparation, не перезаписывается;
- обычная preparation failure по-прежнему fail-closed даёт `failed` с redaction;
- изменены только runner, профильные тесты и обязательный worklog;
- GitHub CI проходит на exact head ветки.

## После завершения

### Фактически сделано

- добавлен `_TERMINAL_RUN_STATUSES` для `completed`, `failed`, `cancelled`;
- добавлена централизованная проверка `_run_is_terminal()`;
- `_execute()` прекращает работу до записи preparation event для terminal run;
- `_record_workspace_preparation_failure()` сохраняет terminal запись без
  изменений;
- regression coverage проверяет все terminal statuses;
- отдельный race test переводит run в `cancelled` внутри preparation, затем
  имитирует clone failure и подтверждает сохранение cancellation.

### Миграции и совместимость

- SQL migrations отсутствуют;
- формат существующих run records не меняется;
- новые поля в API, schema и persisted state не добавляются;
- `queued` и `running` продолжают обрабатываться прежним lifecycle;
- обычная workspace preparation failure по-прежнему записывает terminal
  `failed`, `finished_at`, redacted `error` и trusted event;
- compose, systemd, AppArmor, seccomp и coder images не изменяются.

### Проверки до публикации PR

На изолированном maintenance workspace:

- расширенный Hermes/Codex suite: `184 passed, 1 skipped, 28 subtests passed`;
- cancellation race probe: `PASS`;
- production coder containers не менялись, оба healthy, `init=true`;
- restart count: `0`;
- zombies: `0`;
- evidence manifest SHA-256:
  `60493ece0535e7256614dabbf7833b974c418181ce9bcfa580661e72c9726ed1`.

### PR и commits

- PR: `#597` — `Hermes coder: preserve terminal status during workspace preparation`;
- implementation commit: `ef3f73fda4427e100c80952d94393df8fc44abba`;
- tests commit: `961ac6cc2a62f2b6df9169215b1efe0f8779427d`;
- merge и rollout допускаются только после зелёных обязательных checks.

### Риски и ограничения

- `hermes-coders.service` остаётся failed из-за nested `bwrap --proc` smoke;
- этот PR намеренно не ослабляет bubblewrap/AppArmor/seccomp contract;
- production rollout и coder run submission из feature branch не выполнялись;
- параллельный Kael plugin PR `#596` не входит в scope.

### Незавершённое

- обязательные GitHub checks на exact head PR `#597`;
- независимый review итогового diff;
- merge после зелёного CI;
- controlled production update и post-deploy health verification;
- отдельное исправление nested bubblewrap runtime smoke без ослабления sandbox.

### Следующий шаг

Получить зелёный GitHub CI на exact head, выполнить независимый review и только
после merge применить controlled production update без смешивания с `#596`.
