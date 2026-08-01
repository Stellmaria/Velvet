# Сессия: сущности Каэля, Velvet Librarian и coder-агентов

- Дата: 2026-08-01
- ID: `kael-librarian-personas-20260801`
- Линия/фаза: Hermes identities, project context и runtime isolation
- Статус: `частично`
- Ветка: `agent/kael-librarian-personas`
- Базовый commit: `b1c15532566674f423f64776efba934123ddca6d`

## Перед началом

### Цель

Разделить личность, проектные инструкции и runtime-права серверных Hermes-инстансов согласно документации Hermes Agent:

- основной серверный Hermes переименовать в Каэля;
- создать отдельную сущность и runtime Velvet Librarian;
- оформить отдельные сущности Velvet Coder и Макса;
- устранить подтверждённые permission failures `opsctl.py`, `coderctl.py`, `tasks.json` и `tasks.json.lock`;
- исключить использование coderctl для остановки собственных incident Runs Каэля.

### Исходный контекст

Storage Librarian из PR #535 выполнялся через основной Hermes endpoint и имел только request-level instructions. `SOUL.operator.md` и coder `SOUL.md` смешивали личность с runtime, Git, БД и orchestration procedures. Production-логи подтвердили root-owned `/opt/data/tools` и orchestration ledger. Main Hermes API поддерживает `POST /v1/runs/{run_id}/stop`, но operator пытался использовать coderctl. Telegram topics уже созданы: Inbox `2476`, Hermes Reports `2478`.

### Планируемый объём

- отдельные SOUL/AGENTS для Каэля, Librarian и coder-агентов;
- отдельный internal-only Librarian runtime;
- dedicated Librarian API key и endpoint;
- deny-all tool contract;
- безопасный runctl для собственных Runs Каэля;
- воспроизводимый reconcile прав и context files;
- systemd lifecycle, installers, tests и runbook.

### Критерии готовности

- SOUL содержит личность, а не проектные процедуры;
- project/runtime rules находятся в AGENTS/.hermes.md;
- Librarian не имеет Telegram/GitHub token, host port, terminal/file/web/browser/memory/delegation/code tools;
- Каэль может читать opsctl/coderctl/runctl и писать orchestration ledger;
- coder workspaces получают generated `.hermes.md` без dirty Git status;
- отдельные API keys Каэля, Librarian и coder-агентов;
- CI и production smoke зелёные.

### Риски и ограничения

Отдельный Hermes runtime увеличивает постоянное потребление памяти. Provider routing копируется из проверенного профиля Каэля и требует production smoke. Автоматическая публикация в Hermes Reports не входит в этот срез. Max incident monitor остаётся выключенным до отдельного исправления дедупликации restart-loop.

## После завершения

### Фактически сделано

- добавлены `SOUL.kael.md` и `AGENTS.kael.md`;
- добавлен безопасный `runctl.py` для статуса/остановки собственных Runs Каэля;
- coder личности отделены от `AGENTS.velvet.md` и `AGENTS.max.md`;
- Max coder получил имя Макс;
- добавлены `SOUL.md` и `AGENTS.md` Velvet Librarian;
- добавлен отдельный internal-only `librarian-hermes` Compose stack;
- добавлена подготовка профиля с пустым API whitelist и глобальным deny-list;
- добавлены dedicated endpoint/key, systemd lifecycle и installer;
- добавлен boot reconcile сущностей, инструментов и ledger permissions;
- generated `.hermes.md` исключается через `.git/info/exclude`;
- runbook обновлён с правильной проверкой таблиц `telegram_storage_analysis*`;
- добавлены contract tests.

### Миграции и совместимость

Новых SQL-миграций нет, `z031` не изменяется. Generic `HERMES_BASE_URL/HERMES_API_KEY` сохраняются для Каэля и incident integration. Dedicated Librarian variables имеют fallback на старые generic variables для мягкого обновления.

### Проверки

На head `24be555cfeae99c2fb8832e8ab75af262481cbe0` прошли:

- полный tests workflow и четыре test shards;
- architecture preflight;
- type check;
- project notes contract;
- Docker Compose validation;
- сборка Velvet, Supervisor proxy, VL, Krita, Hermes coder и operator/router images;
- Krita plugin smoke.

Production install и Telegram smoke выполняются только после merge.

### PR и commit

- PR: `https://github.com/Stellmaria/Velvet/pull/538`;
- проверенный runtime head: `24be555cfeae99c2fb8832e8ab75af262481cbe0`;
- merge commit: ожидается после проверки и явного разрешения владельца.

### Незавершённое

- production установка `hermes-entities` и `hermes-librarian`;
- проверка Telegram display name Каэля;
- ручной `/storage_analyze ID` через отдельного Velvet Librarian;
- исправление Max incident dedup и повторное включение его monitor.

### Следующий шаг

После merge обновить VPS, выполнить `deploy/hermes-entities/install.sh` и `deploy/hermes-librarian/install.sh`, проверить сущности и права, затем провести manual-first Librarian smoke-test.
