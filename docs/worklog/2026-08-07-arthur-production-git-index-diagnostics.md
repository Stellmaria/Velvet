# Сессия: read-only diagnostics production Git index Arthur

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-production-git-index-diagnostics`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `ops/arthur-git-index-diagnostics`
- Базовый commit: `ea262da74860c5538a913c3f6af7d8a9468b92ab`
- PR: pending

## Перед началом

### Цель

Получить точное read-only evidence владельца и режима production `.git/index` после fixed-target Librarian reconcile, прежде чем выполнять какой-либо ownership repair.

### Исходный контекст

Rollout run `31192847516` прошёл immutable preflight и bounded backup repair, но canonical server deploy остановился до code deployment на `fatal: .git/index: index file open failed: Permission denied`. Initial production checkout оставался `558f846040fed92ac3935f2fce2dcbd52a284946`. Post-deploy immutable image pin не выполнялся, потому что canonical deploy не завершился.

История проекта уже содержит PR #636, который запретил запуск `deploy/server/deploy.sh` не владельцем checkout и защитил `git reset --hard` безопасным `umask 022`. Текущий drift возник позже: fixed Hermes reconcile host bridge работает как root и проверяет clean checkout через `git status`, что потенциально может обновлять Git index как root.

### Планируемый объём

- расширить существующий production diagnostics workflow только read-only stat-проверками Git metadata;
- вывести deploy UID/GID и owner/mode для checkout root, `.git`, `.git/index` и top-level `.git` files;
- исправить diagnostics false-clean: отдельно фиксировать exit code `git status` и использовать `GIT_OPTIONAL_LOCKS=0`;
- не менять файлы, systemd, Docker, models, env или database;
- после evidence выбрать минимальный one-time repair и durable reconcile fix.

### Критерии готовности

- protected CI diagnostics PR зелёный;
- production probe завершён без mutation;
- подтверждены exact owner/mode `.git/index` и deploy UID/GID;
- `git status` failure больше не маскируется как clean;
- evidence достаточно для bounded repair только затронутых Git metadata.

### Риски и ограничения

Workflow не читает содержимое `.git` metadata, а выводит только filenames/uid/gid/mode. Git status запускается с `GIT_OPTIONAL_LOCKS=0` и его stdout не публикуется. Никаких Arthur credentials кроме обычных deploy SSH secrets workflow не получает. Production application source/image pair не меняется.

## После завершения

### Фактически сделано

Diagnostics workflow расширен owner/mode evidence для checkout и top-level Git metadata. Ошибка `git status` теперь фиксируется через явный return code и не интерпретируется как clean tree.

### Миграции и совместимость

Миграций и runtime changes нет. Workflow исключительно read-only и использует общую `velvet-production` concurrency group.

### Проверки

Production probe ещё не запущен. До merge требуется protected CI и проверка current main.

### PR и commit

- Ветка: `ops/arthur-git-index-diagnostics`.
- База: `ea262da74860c5538a913c3f6af7d8a9468b92ab`.
- Diagnostics workflow commit: `39cad39c035804536e248e48f2454b01a561dee1`.

### Незавершённое

- открыть PR и пройти protected CI;
- выполнить read-only probe;
- подтвердить ownership root cause;
- реализовать one-time index repair и durable root reconcile non-mutating Git probe;
- повторить verified Arthur rollout и дальнейший live acceptance #586.

### Следующий шаг

Слить diagnostics-only PR после зелёного CI, получить production stat evidence и только после этого формировать bounded ownership remediation.
