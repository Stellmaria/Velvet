# Codex SQLite runtime home hotfix

- Дата: 2026-08-08
- ID: codex-sqlite-runtime-home-20260808
- Линия/фаза: Hermes Coder / Codex availability runtime
- Статус: завершено
- Ветка: fix/codex-sqlite-runtime-home
- Базовый commit: 89489278602af0eaf01e7f87212ef6b07dba9790

## Перед началом

### Цель

Восстановить live `account/rateLimits/read` для dynamic Codex availability gate, не делая защищённый `CODEX_HOME` writable.

### Исходный контекст

- rollout dynamic availability gate завершился успешно, coder/router runtime healthy;
- startup availability probe для Velvet и Max завершился fail-closed с `failed to initialize sqlite state runtime under /opt/codex`;
- `CODEX_HOME=/opt/codex` хранит project-scoped auth/config и AppArmor разрешает этому дереву только read;
- `/opt/codex-runs` является отдельным writable per-project bind mount и уже разрешён AppArmor для runtime state;
- актуальный Codex поддерживает отдельный `CODEX_SQLITE_HOME`, который определяет директорию SQLite state независимо от `CODEX_HOME`.

### Планируемый объём

- оставить `CODEX_HOME=/opt/codex` без изменения;
- добавить `CODEX_SQLITE_HOME=/opt/codex-runs/sqlite` в общий coder runtime contract;
- сохранить per-project isolation за счёт существующих отдельных `codex-runs/velvet` и `codex-runs/max` bind mounts;
- добавить regression test на split auth/runtime boundary и AppArmor permissions;
- пройти protected CI и затем controlled production rollout.

### Планируемый контракт

- auth/config остаются под `/opt/codex` и не получают write permissions;
- SQLite state app-server пишется только под `/opt/codex-runs/sqlite`;
- Velvet и Max не делят SQLite state между собой;
- `codex_available` остаётся fail-closed, пока live probe не завершится успешно;
- пятичасовой cadence и manual hold/clear semantics не меняются.

### Риски и ограничения

- реальный provider probe невозможно полностью воспроизвести в CI без production ChatGPT auth context;
- regression test проверяет canonical Compose/AppArmor boundary, а production smoke после rollout подтверждает фактический app-server init;
- существующие SQLite файлы под `/opt/codex`, если они появились ранее, не удаляются автоматически этим hotfix.

### Миграции и совместимость

- database migration приложения Velvet не требуется;
- ChatGPT auth.json и config.toml не перемещаются;
- новый SQLite runtime каталог может быть создан Codex автоматически внутри существующего writable volume;
- Byesu fallback, GPT Image 2 high-res export и model routing не меняются.

### Критерии готовности

- Compose содержит `CODEX_SQLITE_HOME=/opt/codex-runs/sqlite` при неизменном `CODEX_HOME=/opt/codex`;
- AppArmor по-прежнему оставляет `/opt/codex/**` read-only и `/opt/codex-runs/**` writable;
- protected CI зелёный;
- после rollout `codex_availability_ctl.py refresh` возвращает provider snapshot без SQLite startup error.

## После завершения

### Фактически сделано

- в общем coder Compose anchor добавлен `CODEX_SQLITE_HOME: /opt/codex-runs/sqlite`;
- project-scoped auth/config home оставлен неизменным;
- добавлен regression contract на split SQLite/auth boundary и существующие AppArmor permissions;
- hotfix синхронизирован с актуальным `main` после параллельных изменений.

### Проверки

- два предыдущих synchronized hotfix heads уже прошли полный набор из 6 required checks;
- после финального sync с `main` полный protected CI выполняется заново на exact head;
- production provider smoke выполняется только после merge и controlled rollout.

### PR и commit

- PR: #710 `Fix Codex app-server SQLite runtime boundary`;
- ветка: `fix/codex-sqlite-runtime-home`;
- текущий базовый commit: `89489278602af0eaf01e7f87212ef6b07dba9790`;
- final tested head и merge commit фиксируются после последнего CI.

### Незавершённое

- production rollout после merge;
- live smoke `codex_availability_ctl.py status/refresh` для Velvet и Max;
- подтверждение реального provider state: `provider_available` boolean, populated `rate_limits`, no SQLite startup error.

### Следующий шаг

Пройти protected CI на exact head после финального sync, выполнить exact-head merge и controlled production rollout.
