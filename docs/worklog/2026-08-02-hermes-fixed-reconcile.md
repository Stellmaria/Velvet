# Сессия: фиксированный reconcile Hermes-инфраструктуры

- Дата: 2026-08-02
- ID: `hermes-fixed-reconcile-20260802`
- Линия/фаза: Hermes operator / production lifecycle
- Статус: `частично`
- Ветка: `feat/hermes-fixed-reconcile`
- Базовый commit: `3bbb7ba453b8244334f354d75ebba7f59ebf60cd`

## Перед началом

### Цель

Закрыть разрыв между обычным `opsctl velvet update` и обязательной переустановкой host/systemd частей Hermes после merge. Каэль должен уметь после отдельного разрешения владельца применить только заранее определённые installers для coder runtime, сущностей и Storage Librarian, не получая root, Docker socket, systemd API или произвольный shell.

### Исходный контекст

1 августа 2026 года GitHub `main` получил изменения сущностей, Librarian и runtime smoke кодеров. Обычный deployment Velvet не гарантирует переустановку этих host units. Поэтому код мог быть слит, а production продолжал работать на старой конфигурации.

Ручной SSH остаётся необходимым для каждого такого изменения. Это создаёт незамкнутый операторский цикл:

```text
merge → Velvet update → ручной sudo installer → ручной systemctl → smoke
```

Существующий `hermes-operator-host.service` намеренно имеет только непривилегированный fixed start и не должен расширяться до root/systemd.

### Планируемый объём

- добавить отдельный root host bridge с фиксированным allowlist;
- добавить непривилегированный internal-only HTTP gateway;
- добавить `reconcilectl.py` в data directory Каэля;
- сделать задачи асинхронными, чтобы self-restart Каэля не прерывал host-операцию;
- хранить очищенный lifecycle последних задач;
- проверять clean `main` и совпадение `HEAD` с уже fetched `origin/main`;
- добавить installer, systemd units, документацию и contract tests;
- не изменять параллельные installers из PR #541.

### Критерии готовности

- Каэль принимает только цели `coders`, `entities`, `librarian`, `all`;
- произвольные команды, пути, service names и commit SHA не принимаются;
- reconcile не выполняет Git fetch, checkout, reset или merge;
- задача создаётся только на чистом `main`, совпадающем с fetched `origin/main`;
- `all` выполняется в порядке `coders → librarian → entities`;
- self-restart Каэля не прерывает host-задачу;
- `accepted`, `queued` и `running` не считаются успехом;
- ошибки очищаются от token-like значений;
- focused tests и полный GitHub Actions CI проходят;
- после production install live smoke подтверждает coder auth/push, entities и Librarian.

### Риски и ограничения

Root bridge необходим, потому что installers управляют systemd и защищёнными host-файлами. Риск ограничен отдельным process boundary, фиксированными командами, неизменяемым allowlist, root-only state и systemd hardening. Каэль не получает root shell, Docker socket или systemd API.

Первичная установка самого reconcile-контура всё равно требует одного доверенного ручного запуска через SSH. После этого последующие известные Hermes installers можно применять через фиксированный маршрут.

Контур не управляет host Supervisor проекта Max. Обязательный доверенный restart `romatic-server-supervisor.service` остаётся отдельной host-операцией.

## После завершения

### Фактически сделано

- создан `deploy/hermes-reconcile/host_reconcile.py`;
- разрешены только цели `coders`, `entities`, `librarian`, `all`;
- `all` выполняет фиксированный порядок `coders → librarian → entities`;
- submit возвращает `task_id` до начала installers;
- добавлены `status`, `wait` и `list`;
- состояние последних 100 задач хранится root-only и обновляется атомарно;
- queued/running задача после restart host bridge маркируется failed;
- добавлен отдельный HTTP gateway без published ports, Docker socket, production checkout и supervisor network;
- добавлен отдельный root systemd unit с hardening и фиксированным `/usr/local/libexec` entrypoint;
- добавлен installer, который сохраняет существующий operator token и создаёт отдельный reconcile token без вывода;
- обновлён операционный контракт Каэля;
- добавлены runtime и static contract tests;
- открыт PR #542.

### Миграции и совместимость

SQL-миграций нет. Production базы данных и существующие supervisor routes не меняются. Старый `opsctl` и непривилегированный fixed start bridge остаются без изменений.

Новый reconcile-контур устанавливается отдельно и использует существующий operator client token только для аутентификации Каэля. Для host socket создаётся отдельный token. Параллельный PR #541 может менять entities и Librarian installers, а reconcile вызывает их по стабильным путям и не дублирует их содержимое.

### Проверки

До PR локально прошли:

- `python -m compileall deploy/hermes-reconcile`;
- `bash -n deploy/hermes-reconcile/install.sh`;
- `python -m unittest tests/test_hermes_reconcile_contract.py -v`;
- focused suite: 13 tests, `OK`.

Первый GitHub Actions run выявил только неполный формат worklog. Запись приведена к обязательному проектному контракту. Остальные workflows продолжают полную проверку.

### PR и commit

- PR: `https://github.com/Stellmaria/Velvet/pull/542`;
- ветка: `feat/hermes-fixed-reconcile`;
- head до исправления worklog: `c021dc134b08661deabf7ae76b20453ae52810cd`;
- финальный head будет определён после этого коммита и повторного CI;
- merge commit ожидается только после зелёного CI и явного разрешения владельца.

### Незавершённое

- дождаться полного зелёного CI PR #542;
- слить PR после отдельного разрешения владельца;
- обновить `/srv/velvet`;
- один раз вручную выполнить `sudo bash deploy/hermes-reconcile/install.sh`;
- выполнить live smoke `submit coders` и получить `AUTH_OK, PUSH_OK` для обоих кодеров;
- выполнить live smoke `submit entities` и подтвердить восстановление Каэля;
- выполнить `submit librarian` и проверить manual-first команды;
- отдельно выполнить требуемый host restart Supervisor Max.

### Следующий шаг

После зелёного CI запросить разрешение на merge PR #542. Затем отдельно обновить production Velvet, один раз установить reconcile-контур через SSH и выполнить три поэтапных live smoke вместо немедленного `submit all`, чтобы точно локализовать возможный первый production blocker.
