# Сессия: owner-authorized merge и controlled rollout #581

- Дата: 2026-08-04
- ID: `owner-rollout-issue-581-20260804`
- Линия/фаза: hotfix/controlled rollout
- Статус: частично
- Issue: #581
- PR: #582
- Ветка: `hotfix/581-unified-coder-router-sandbox`
- Базовый commit: `eb4849c3ee4461b540d3e1ba0572cf54f82a12d3`
- Reviewed head до авторизации: `17c42fc0746b8aa49a26b547dfe48678e6c8ec3a`

## Перед началом

### Цель

После явного разрешения владельца слить проверенный PR #582 и выполнить отдельный controlled rollout точного merge SHA с rollback и live acceptance.

### Исходный контекст

Code/static review exact head завершён, все обязательные GitHub checks успешны. Production acceptance AppArmor, seccomp, bwrap, systemd и Telegram paths ещё не выполнялся. Автоматический цикл Каэль → coder остановлен владельцем.

### Планируемый объём

- squash-merge только проверенного PR head;
- зафиксировать точный merge SHA из `main`;
- обновить production checkout только на этот SHA;
- установить canonical coder/orchestration runtime;
- выполнить live sandbox, lifecycle и direct/delegated acceptance;
- удалить временный unconfined workaround только после успешных проверок.

### Критерии готовности

Merge подтверждён GitHub и `main`; production checkout совпадает с точным merge SHA; services healthy; AppArmor/seccomp/bwrap и четыре Telegram paths проходят; rollback evidence сохранён; production checkout остаётся clean.

### Риски и ограничения

Merge и rollout являются разными стадиями. Успешный merge не подтверждает production runtime. При любой ошибке rollout временный workaround не удаляется, а services возвращаются к предыдущей конфигурации без удаления volumes, ledger, workspaces или coder data.

## После завершения

### Фактически сделано

Владелец явно разрешил продолжить merge и controlled rollout. GitHub merge API был вызван для reviewed head, но до подтверждения нового `main` SHA результат не считается merge. Production не изменялся.

### Миграции и совместимость

Миграций БД нет. До live acceptance сохраняется существующий временный sandbox workaround.

### Проверки

Reviewed head имел успешные required checks. Новый documentation-only head обязан повторно пройти полный PR CI до merge.

### PR и commit

- PR: #582;
- reviewed head: `17c42fc0746b8aa49a26b547dfe48678e6c8ec3a`;
- merge SHA: ожидается после успешного squash-merge.

### Незавершённое

- дождаться CI нового head;
- выполнить squash-merge exact head;
- подтвердить `main` SHA;
- выполнить production rollout и live acceptance;
- обновить issue/worklog фактическими evidence.

### Следующий шаг

Дождаться terminal CI на новом PR head и повторить squash-merge с `expected_head_sha`.
