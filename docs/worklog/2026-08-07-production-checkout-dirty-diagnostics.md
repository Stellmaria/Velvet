# Сессия: production checkout dirty diagnostics

- Дата: `2026-08-07`
- ID: `production-checkout-dirty-diagnostics-20260807`
- Линия/фаза: `production diagnostics / Git checkout`
- Статус: `частично`
- Ветка: `diag/production-dirty-paths-20260807`
- Базовый commit: `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`

## Перед началом

### Цель

Без изменения production определить, какие Git paths делают `/srv/velvet` dirty и блокируют canonical `reconcile coders`.

### Исходный контекст

После успешного `opsctl velvet update` production checkout находился на `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`. Позже `opsctl velvet status` подтвердил тот же local/remote head, но `dirty=true`, поэтому Kael корректно отказался выполнять `reconcilectl.py submit coders`.

Текущий Kael control-plane показывает только boolean dirty state и запрещает direct Git access, поэтому точные paths через разрешённый Kael contour не наблюдаемы.

### Планируемый объём

- добавить отдельный GitHub Actions production diagnostic workflow;
- читать только branch, HEAD, origin/main и Git porcelain status;
- выводить максимум 50 status/path строк без содержимого файлов;
- применять token/credential redaction к диагностическому выводу;
- не выполнять reset, clean, checkout, update, restart или reconcile;
- после merge использовать автоматически запущенный workflow как production evidence.

### Критерии готовности

- protected CI PR зелёный;
- workflow merge-triggered run завершается успешно;
- production head/origin и `working_tree` зафиксированы;
- при dirty checkout получен ограниченный redacted список status/path без file contents.

### Риски и ограничения

Имена файлов сами по себе могут содержать чувствительные фрагменты, поэтому вывод ограничен 50 строками и проходит token-like redaction. Workflow не исправляет dirty checkout и не авторизует последующий reset/reconcile.

## После завершения

### Фактически сделано

- добавлен `.github/workflows/production-checkout-dirty-diagnostics.yml`;
- workflow использует существующий production SSH environment;
- выполняются только read-only Git identity/status команды;
- вывод porcelain status/path ограничен 50 строками;
- содержимое изменённых файлов не читается;
- diagnostic output проходит существующий token/credential redaction.

### Миграции и совместимость

Database migrations отсутствуют. Runtime application, Docker, systemd, Hermes, coder releases и production checkout не изменяются самим workflow. Изменение добавляет только read-only diagnostic path в GitHub Actions.

### Проверки

Первый PR head запустил protected CI. `project notes contract` выявил недостающие canonical sections worklog; структура worklog исправлена по фактическому CI evidence. Остальные protected checks должны повторно пройти на обновлённом PR head.

### PR и commit

- PR: `#691`;
- ветка: `diag/production-dirty-paths-20260807`;
- первый workflow commit: `dcca7da6c1ce23ab6b778f5b569233959fe90484`;
- worklog commit до contract fix: `cc790a75bc0840c2cde4fe74a6dc8b04c775a91a`;
- финальный PR head фиксируется GitHub после этого исправления.

### Незавершённое

- дождаться повторного protected CI;
- merge только после terminal green;
- прочитать автоматически запущенный production diagnostic run;
- отдельно решить судьбу найденных dirty paths.

### Следующий шаг

После зелёного CI слить PR #691 в `main`, дождаться merge-triggered workflow и использовать его read-only output для точной классификации production dirty checkout.
