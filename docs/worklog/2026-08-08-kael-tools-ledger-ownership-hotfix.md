# Kael tools and coder ledger ownership hotfix

- Дата: 2026-08-08
- ID: kael-tools-ledger-ownership-hotfix
- Линия/фаза: Hermes operator and coder orchestration production reliability
- Статус: `завершено`
- Ветка: `hotfix/kael-tools-ledger-ownership`
- Базовый commit: `328749227e26a8bfc8fc39447bf9782b9b040f2a`

## Перед началом

### Цель

Устранить production regression, из-за которого orchestration installer менял владельца persistent Kael tools и coder ledger на host service UID/GID, лишая Hermes runtime доступа к canonical operator clients и возможности безопасно фиксировать delegated coder tasks.

### Исходный контекст

Production Velvet, Hermes, coder agents и coder router были healthy. Read-only `coderctl health all` успешно возвращал authenticated capabilities, но Kael получал `Permission denied` на `/opt/data/tools/opsctl.py`, `monitorctl.py` и `reconcilectl.py`.

Read-only inspection внутри `velvet-hermes-1` показал:

```text
10000:10000 700 /opt/data
1000:1000 750 /opt/data/tools
10000:10000 500 /opt/data/tools/opsctl.py
10000:10000 500 /opt/data/tools/monitorctl.py
10000:10000 500 /opt/data/tools/reconcilectl.py
1000:1000 500 /opt/data/tools/coderctl.py
```

После bounded runtime repair `/opt/data/tools` и `coderctl.py` снова принадлежали `10000:10000`, а запуск canonical tools под UID 10000 завершился `KAEL_TOOLS_OK`.

Root cause найден в `deploy/hermes-orchestration/install.sh`: installer определял owner по родительскому `VELVET_DATA_DIR`, который на production принадлежит host service user, хотя сам persisted Hermes data directory принадлежит Hermes runtime.

Дополнительно `coderctl submit` отправлял задачу central router до локального `ledger.upsert`, поэтому при unwritable ledger был возможен upstream run без локальной durable task record.

### Планируемый объём

- Определять UID/GID Kael runtime по существующему `$hermes_data`, а не по его родительскому каталогу.
- Сохранять этот owner для `$hermes_data/tools`, `$hermes_data/orchestration` и `coderctl.py`.
- Fail closed, если expected Hermes data directory отсутствует.
- Добавить local ledger write preflight до первого network submit в `coderctl.py`.
- Добавить regression coverage для ownership contract и fail-closed submit ordering.
- Не менять router authentication, coder production privileges или production deployment semantics.

### Критерии готовности

- Orchestration installer больше не использует owner `VELVET_DATA_DIR` для Kael persistent tools/ledger.
- `coderctl submit` не вызывает router при failed ledger write preflight.
- Probe preflight не оставляет временные файлы.
- Existing typed router contract не меняется.
- Protected CI checks проходят на final PR head.

### Риски и ограничения

- Изменение ownership должно сохранять существующую Hermes runtime boundary, а не расширять permissions.
- Проверка ledger должна происходить до network submit, иначе возможен orphaned upstream run.
- Production deploy/reconcile не входит в этот PR и выполняется отдельно после merge при явном owner authorization.
- Значения production secrets в worklog не фиксируются.

## После завершения

### Фактически сделано

- `deploy/hermes-orchestration/install.sh` теперь требует существующий `$hermes_data`, читает `hermes_uid`/`hermes_gid` непосредственно с него и сохраняет этот owner для tools, orchestration ledger directory и установленного `coderctl.py`.
- `deploy/hermes-operator/coderctl.py` получил `Ledger.ensure_writable()`.
- Перед central router submit `coderctl` теперь проверяет доступ к lock/ledger и возможность создать временный файл в ledger directory.
- При local ledger permission failure submit fail-closed завершается до network mutation.
- Добавлен focused regression test `tests/test_kael_tools_ledger_ownership_hotfix.py`.

### Миграции и совместимость

SQL migrations отсутствуют. API router schema, authentication и coder routing metadata не менялись. Изменение совместимо с существующим persisted Hermes data: owner берётся из уже существующего каталога и не задаётся новым hardcoded UID.

### Проверки

- Production runtime evidence: после bounded owner repair все четыре canonical tools успешно исполнялись под `uid=10000(hermes)` и вернули `KAEL_TOOLS_OK`.
- PR regression coverage проверяет owner source, отсутствие старого `velvet_uid`/`velvet_gid` contract и fail-closed ordering перед `RouterClient.submit`.
- Protected GitHub CI запущен на PR #708; первый notes run выявил только несоответствие формату worklog, после чего запись приведена к обязательному project-notes contract.

### PR и commit

- PR: #708 `Fix Kael tool and coder ledger ownership`
- Ветка: `hotfix/kael-tools-ledger-ownership`
- Base: `328749227e26a8bfc8fc39447bf9782b9b040f2a`
- Final merge commit фиксируется GitHub после успешных protected checks и merge.

### Незавершённое

Production ещё работает на предыдущем checkout. Репозиторный fix после merge потребует отдельного штатного rollout/reconcile и повторного typed read-only canary. Эти production mutations не входят в текущий GitHub change.

### Следующий шаг

Дождаться всех protected CI checks PR #708, устранить только подтверждённые failures при их наличии и merge PR в `main` при полном green status. После merge отдельно обновить production canonical path и повторить read-only `coder_delegate` canary.
