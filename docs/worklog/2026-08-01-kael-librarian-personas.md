# Сущности Каэля, Velvet Librarian и coder-агентов

Статус: частично

## Перед началом

### Цель

Разделить личность, проектные инструкции и runtime-права серверных Hermes-инстансов согласно документации Hermes Agent:

- основной серверный Hermes переименовать в Каэля;
- создать отдельную сущность и runtime Velvet Librarian;
- оформить отдельные сущности Velvet Coder и Макса;
- устранить подтверждённые permission failures `opsctl.py`, `coderctl.py`, `tasks.json` и `tasks.json.lock`;
- исключить использование coderctl для остановки собственных incident Runs Каэля.

### Исходный контекст

- Storage Librarian из PR #535 выполнялся через основной Hermes endpoint и имел только request-level instructions;
- `SOUL.operator.md` смешивал личность с командами runtime;
- coder `SOUL.md` смешивали личность, Git, БД и orchestration contract;
- production-логи подтвердили root-owned `/opt/data/tools` и orchestration ledger;
- main Hermes API уже поддерживает `POST /v1/runs/{run_id}/stop`, но operator пытался использовать coderctl;
- Telegram topics созданы: Inbox `2476`, Hermes Reports `2478`.

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

- отдельный Hermes runtime увеличивает постоянное потребление памяти;
- provider routing копируется из проверенного профиля Каэля и требует production smoke;
- автоматическая публикация в Hermes Reports не входит в этот срез;
- Max incident monitor остаётся выключенным до отдельного исправления дедупликации restart-loop.

### Базовый commit и ветка

- session: `kael-librarian-personas-20260801`;
- base: `b1c15532566674f423f64776efba934123ddca6d`;
- branch: `agent/kael-librarian-personas`.

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

- новых SQL-миграций нет;
- `z031` не изменяется;
- generic `HERMES_BASE_URL/HERMES_API_KEY` сохраняются для Каэля и incident integration;
- dedicated Librarian variables имеют fallback на старые generic variables для мягкого обновления.

### Проверки

- локальные/CI проверки: ожидаются;
- production install и Telegram smoke: ожидаются после merge.

### Незавершённое

- полный CI;
- production установка `hermes-entities` и `hermes-librarian`;
- ручной `/storage_analyze ID`;
- исправление Max incident dedup и повторное включение его monitor.

### Следующий шаг

Запустить CI, устранить contract/inventory drift, слить PR после явного разрешения и выполнить два installer на VPS с manual-first smoke-test.
