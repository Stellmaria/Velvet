# Сессия: Hermes reconcile launcher writable paths

- Дата: `2026-08-07`
- ID: `hermes-reconcile-launcher-writable-paths-20260807`
- Линия/фаза: `Hermes / production reconcile hardening`
- Статус: `частично`
- Ветка: `hotfix/hermes-reconcile-launcher-writable-paths`
- Базовый commit: `940b5eaf780fac268943dce883769a6433c98994`
- Failed reconcile task: `reconcile_6b126d2366c048a7b454bd1fc4c56ecb`

## Перед началом

### Цель

Исправить подтверждённый systemd sandbox contract bug, из-за которого fixed root reconcile bridge не мог выполнить заранее разрешённый canonical `coders` installer.

### Исходный контекст

После успешного verified-image production bootstrap production checkout был clean и находился на exact main `940b5eaf780fac268943dce883769a6433c98994`. Один owner-authorized `reconcile coders` завершился terminal `failed` при staging exact-SHA sandbox launcher release:

`mktemp: failed to create directory via template '/usr/local/lib/hermes-sandbox-launcher/releases/.stage-940b5eaf780fac268943dce883769a6433c98994.XXXXXX': Read-only file system`

Canonical `deploy/hermes-sandbox-launcher/install.sh` обязан атомарно staging-ить releases под `/usr/local/lib/hermes-sandbox-launcher/releases` и устанавливать AppArmor profiles под `/etc/apparmor.d`. При этом `hermes-operator-reconcile.service` сохранял `ProtectSystem=strict`, но его `ReadWritePaths` не разрешал запись ни в launcher root, ни в AppArmor profile directory.

### Планируемый объём

- сохранить `ProtectSystem=strict` и остальные systemd hardening controls;
- добавить только `/usr/local/lib/hermes-sandbox-launcher` и `/etc/apparmor.d` в fixed `ReadWritePaths` root bridge;
- не разрешать широкие `/usr/local` или `/etc`;
- обеспечить существование launcher root до старта reconcile unit;
- добавить regression coverage для writable-path boundary;
- не менять allowlist reconcile targets или arbitrary-command boundary.

### Критерии готовности

- canonical `coders` installer получает запись только в host paths, которые ему уже необходимы;
- reconcile root bridge остаётся sandboxed через `ProtectSystem=strict`;
- `/usr/local` и `/etc` целиком не становятся writable;
- fresh install заранее создаёт `/usr/local/lib/hermes-sandbox-launcher` как `root:root 0755`;
- focused reconcile contract tests проходят;
- protected GitHub CI проходит перед merge.

### Риски и ограничения

Изменение расширяет writable host surface root reconcile bridge, но только на два exact path, уже используемых фиксированным canonical installer. Оно не предоставляет Каэлю shell, Docker socket, произвольные пути или произвольные systemd commands. После merge production unit должен быть переустановлен через canonical `deploy/hermes-reconcile/install.sh`; одного Git checkout update недостаточно для уже загруженного systemd unit.

## После завершения

### Фактически сделано

- `deploy/systemd/hermes-operator-reconcile.service` сохраняет `ProtectSystem=strict` и добавляет exact writable paths:
  - `/usr/local/lib/hermes-sandbox-launcher`;
  - `/etc/apparmor.d`.
- `deploy/hermes-reconcile/install.sh` заранее создаёт `/usr/local/lib/hermes-sandbox-launcher` как `root:root 0755` до установки/restart reconcile service.
- `tests/test_hermes_reconcile_contract.py` проверяет exact launcher/AppArmor writable paths и одновременно запрещает широкие `/usr/local` и `/etc`.
- allowlist targets `coders`, `entities`, `librarian`, `all` и запрет arbitrary shell не менялись.

### Миграции и совместимость

SQL-миграций нет. Изменение относится только к host systemd sandbox и canonical reconcile installer. Существующий launcher release layout и AppArmor profile paths не меняются.

### Проверки

Protected GitHub CI будет запущен на exact PR head. Отдельно ожидаются `hermes reconcile` contract checks, поскольку изменены `deploy/hermes-reconcile/**`, reconcile systemd unit и focused test.

### PR и commit

- Ветка: `hotfix/hermes-reconcile-launcher-writable-paths`.
- Базовый commit: `940b5eaf780fac268943dce883769a6433c98994`.
- PR и merge SHA будут зафиксированы после protected CI.

### Незавершённое

- открыть PR;
- дождаться terminal green protected CI;
- merge в `main`;
- обновить production checkout до exact нового main;
- canonical reinstall `deploy/hermes-reconcile/install.sh`;
- повторить ровно один `reconcile coders` и дождаться terminal state;
- только после completed выполнить health и typed read-only canary.

### Следующий шаг

Открыть узкий hotfix PR, проверить exact diff и дождаться всех обязательных CI checks перед merge.
