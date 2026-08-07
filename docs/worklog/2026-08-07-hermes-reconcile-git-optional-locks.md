# Сессия: Hermes reconcile read-only Git verification

- Дата: 2026-08-07
- ID: `2026-08-07-hermes-reconcile-git-optional-locks`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `fix/hermes-reconcile-readonly-git`
- Базовый commit: `138a47b893c4ffe12128e0e60e2e3d584c9cefc6`
- PR: pending

## Перед началом

### Цель

Устранить durable ownership drift production `.git/index`, создаваемый root Hermes reconcile bridge во время read-only checkout verification, и определить возможность канонической переустановки bridge через существующий passwordless sudo contract.

### Исходный контекст

Rollout run `31192847516` остановился до deployment mutation с `fatal: .git/index: index file open failed: Permission denied`. Read-only diagnostics run `31193612593` подтвердил exact state: deploy user `uid=1000 gid=1000`, checkout root и `.git` принадлежат `1000:1000`, все остальные top-level Git metadata также принадлежат deploy user, но `.git/index` единственный имеет `uid=0 gid=0 mode=640`. `git status` от deploy user возвращает `128`.

Production Hermes reconcile unit запускает `/usr/local/libexec/velvet-hermes-operator-reconcile-entrypoint.py` от root. Entry point оборачивает все checkout verification Git commands через exact `safe.directory`, но ранее не отключал optional Git locks/index refresh. Root `git status` поэтому мог переписать index с unit `UMask=0027`, получая наблюдаемый `root:root 0640`.

### Планируемый объём

- в production reconcile entrypoint добавить global Git option `--no-optional-locks` ко всем verification Git calls;
- сохранить exact `safe.directory`, fixed targets и отсутствие `git fetch`/arbitrary shell surface;
- добавить regression test command shape;
- расширить read-only Arthur diagnostics только проверкой `sudo -n -l` для exact canonical `deploy/hermes-reconcile/install.sh`;
- не менять application source/image pair, Arthur queue policy, vision scope или production runtime в этом PR.

### Критерии готовности

- protected CI полностью зелёный;
- Git verification regression test требует `--no-optional-locks`;
- merge запускает только read-only diagnostics workflow;
- diagnostics подтверждает `reconcile_installer_sudo=allowed` либо `denied` без выполнения installer;
- subsequent rollout выполняет one-time repair только подтверждённого `.git/index` и не расширяет ownership mutation на весь checkout.

### Риски и ограничения

Изменение entrypoint само по себе не меняет уже запущенный root reconcile process. Для production activation требуется каноническая переустановка/restart bridge через `deploy/hermes-reconcile/install.sh` или отдельный контролируемый root operation. Именно поэтому PR также проверяет существующий sudo contract read-only способом. Текущий повреждённый `.git/index` всё равно требует one-time ownership repair перед следующим canonical deploy.

## После завершения

### Фактически сделано

`deploy/hermes-reconcile/host_reconcile_entrypoint.py` теперь формирует Git command как `/usr/bin/git --no-optional-locks -c safe.directory=<exact checkout> -C <checkout> ...`. Это сохраняет read-only checkout verification и запрещает Git выполнять необязательные index/lock updates от root.

`tests/test_hermes_reconcile_checkout_entrypoint.py` обновлён: regression test проверяет и `--no-optional-locks`, и exact `safe.directory`, одновременно запрещая wildcard `safe.directory=*`.

`.github/workflows/arthur-production-diagnostics.yml` получил read-only capability probe `sudo -n -l /usr/bin/bash <APP_DIR>/deploy/hermes-reconcile/install.sh`, выводящий только `allowed/denied`.

### Миграции и совместимость

SQL/application migrations отсутствуют. Изменён только host reconcile entrypoint, его тест и diagnostics workflow. Файлы не входят в application image publish path contract; verified Arthur source/image pair остаётся прежним, если до rollout не появятся новые application-image changes в main.

### Проверки

Production ownership evidence уже зафиксирован diagnostics run `31193612593`: `.git/index=root:root 0640`, остальные top-level Git metadata принадлежат deploy user. Protected CI и sudo capability probe после merge ещё не завершены.

### PR и commit

- Ветка: `fix/hermes-reconcile-readonly-git`.
- База: `138a47b893c4ffe12128e0e60e2e3d584c9cefc6`.
- Entry point fix commit: `ba17018d09ccc776899960ac9dfc8cc2f6478677`.
- Regression test commit: `86e9042f5eeb827892cc7fbef0d3a48a8d110402`.
- Diagnostics capability commit: `b00954d43a6bd9edafb7a30586b3b568e02912ad`.

### Незавершённое

- открыть PR и пройти protected CI;
- выполнить read-only sudo capability probe;
- построить bounded rollout: repair только `.git/index`, canonical deploy, immutable image pin, activation исправленного reconcile bridge, fixed-target Librarian reconcile и Arthur gates;
- после automated acceptance выполнить manual live workflow и resource/restart persistence evidence #586.

### Следующий шаг

Слить durable fix после зелёного CI, определить exact canonical reconcile-installer sudo capability и затем сформировать следующий production rollout без speculative privilege assumptions.
