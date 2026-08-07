# Сессия: production checkout dirty diagnostics

- Дата: `2026-08-07`
- ID: `production-checkout-dirty-diagnostics-20260807`
- Линия/фаза: `production diagnostics / Git checkout`
- Статус: `частично`
- Базовый commit: `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`

## Перед началом

### Цель

Без изменения production определить, какие Git paths делают `/srv/velvet` dirty и блокируют canonical `reconcile coders`.

### Исходный контекст

После успешного `opsctl velvet update` production checkout находился на `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`. Позже `opsctl velvet status` подтвердил тот же local/remote head, но `dirty=true`, поэтому Kael корректно отказался выполнять `reconcilectl.py submit coders`.

Текущий Kael control-plane показывает только boolean dirty state и запрещает direct Git access, поэтому точные paths через разрешённый Kael contour не наблюдаемы.

### Изменение

Добавлен отдельный GitHub Actions workflow `.github/workflows/production-checkout-dirty-diagnostics.yml`, который после merge собственного файла:

- использует существующий production SSH environment;
- выполняет только read-only Git identity/status команды;
- не читает содержимое изменённых файлов;
- выводит porcelain status и path максимум для 50 записей;
- пропускает вывод через существующий token/credential redaction;
- не выполняет reset, checkout, clean, update, restart или reconcile.

### Критерии готовности

- protected CI PR зелёный;
- workflow merge-triggered run завершается успешно;
- production head/origin и `working_tree` зафиксированы;
- при dirty checkout получен ограниченный redacted список status/path без file contents.

### Риски и ограничения

Имена файлов сами по себе могут содержать чувствительные фрагменты, поэтому вывод ограничен 50 строками и проходит token-like redaction. Workflow не исправляет dirty checkout и не авторизует последующий reset/reconcile.

## После завершения

### Незавершённое

- открыть PR;
- дождаться protected CI;
- merge после зелёных checks;
- прочитать автоматически запущенный production diagnostic run;
- отдельно решить судьбу найденных dirty paths.
