# Hermes reboot persistence fixes

- Дата: 2026-08-07
- ID: hermes-reboot-persistence-2026-08-07
- Линия/фаза: Hermes / post-reboot infrastructure hardening
- Статус: завершено
- Ветка: `fix/hermes-sandbox-runtime-directory`
- Базовый commit: `7b561b0bb2d04b7d5fd4fa3ae084d9af830c424f`

## Перед началом

### Цель

Закрепить в исходном репозитории два исправления, обнаруженные после production reboot: создание приватного runtime-каталога sandbox launcher средствами systemd и исполняемый режим entity reconciler.

### Исходный контекст

После перезагрузки `hermes-entities-reconcile.service` завершался с `203/EXEC`, потому что `deploy/hermes-entities/reconcile.sh` не имел исполняемого Git-режима. `hermes-sandbox-launcher.service` завершался с `226/NAMESPACE`, потому что volatile-каталог `/run/hermes-sandbox-private` отсутствовал до применения `ReadWritePaths=`.

### Планируемый объём

- Сохранить `deploy/hermes-entities/reconcile.sh` с Git-режимом `100755` без изменения содержимого.
- Добавить `RuntimeDirectory=hermes-sandbox-private` и `RuntimeDirectoryMode=0700` в canonical launcher unit.
- Добавить regression coverage в deployment-contract tests.

### Критерии готовности

- Reconciler сохраняется как executable в Git.
- Systemd создаёт приватный runtime-каталог при запуске launcher.
- Контрактные тесты фиксируют оба требования.
- Обязательные CI checks проходят перед merge.

### Риски и ограничения

Изменение не должно перезапускать production-сервисы или менять секреты. Локальный server drop-in остаётся безопасной временной страховкой до штатного применения обновлённого installer/unit.

## После завершения

### Фактически сделано

- `deploy/hermes-entities/reconcile.sh` переведён с режима `100644` на `100755` без изменения содержимого.
- В `deploy/systemd/hermes-sandbox-launcher.service` добавлены `RuntimeDirectory=hermes-sandbox-private` и `RuntimeDirectoryMode=0700`.
- В `tests/test_hermes_sandbox_deployment_contract.py` добавлены regression assertions для runtime directory и executable mode.

### Миграции и совместимость

Миграции данных не требуются. Изменение совместимо с существующей unit-конфигурацией и заменяет необходимость заранее создавать volatile-каталог в `/run`.

### Проверки

- `systemd-analyze verify` для launcher unit проходит с заглушками внешних зависимостей.
- Deployment-contract tests покрывают оба исправления.
- После production reboot launcher probes, coder gateways, router и прикладные сервисы были подтверждены healthy.
- Финальное слияние выполняется только после обязательных GitHub checks.

### PR и commit

- PR: #666 `Fix Hermes sandbox runtime directory and reconciler mode`.
- Ветка: `fix/hermes-sandbox-runtime-directory`.
- Итоговый merge commit будет создан GitHub после прохождения protected checks.

### Незавершённое

Нет незавершённых изменений в рамках этого PR. Применение canonical unit на production выполняется отдельным штатным deployment-процессом после merge, без ручного вмешательства в работающие сервисы.

### Следующий шаг

Дождаться зелёных protected checks и выполнить squash-merge PR #666 в `main`.
