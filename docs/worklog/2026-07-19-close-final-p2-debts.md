# Сессия: закрытие последних долгов P2

- Дата: 2026-07-19
- ID: `2026-07-19-close-final-p2-debts`
- Линия/фаза: Velvet Archive, P2AO–P2AP
- Статус: `завершено`
- Ветка: `agent/close-final-p2-debts`
- Базовый commit: `691cb0d4c44cb09c72c15edcae955865639776dc`

## Перед началом

### Цель

Проверить и закрыть последние четыре unresolved broad exception boundary в `system_health.py` и `workers/manager.py`, сохранив корректную изоляцию отказов и терминальное поведение отмены задач.

### Исходный контекст

После P2AN инвентарь содержал 67 широких перехватов, из которых 63 были проверены, а 4 оставались unresolved в двух файлах. Callback-долги уже были закрыты до нуля.

### Планируемый объём

- проверить две границы health-check;
- проверить границу одной итерации worker;
- проверить аварийную границу периодического цикла worker;
- добавить регрессионные тесты для ошибок и отмены;
- обновить P2-инвентарь до нулевого остатка.

### Критерии готовности

- ошибка PostgreSQL не мешает проверить Telegram и возвращается в health-report;
- ошибка Telegram не уничтожает весь health-report;
- `asyncio.CancelledError` не поглощается;
- worker фиксирует сбой итерации и остаётся управляемым;
- авария самого цикла фиксируется как terminal worker failure;
- `broad_exception_unresolved == 0` и CI зелёный.

### Риски и ограничения

Широкие перехваты сохраняются только как внешние границы подсистем. Они не должны превращаться в молчаливое игнорирование: состояние отказа записывается, ошибка логируется, а отмена пробрасывается.

## После завершения

### Фактически сделано

- health probes получили явный проброс `asyncio.CancelledError`;
- database и Telegram probe boundaries классифицированы и покрыты тестами;
- worker iteration и worker loop boundaries классифицированы и покрыты тестами;
- проверены обновление snapshot, счётчики отказов, `next_run_at` и terminal loop state;
- P2 broad exception backlog доведён с 4 до 0.

### Миграции и совместимость

Миграции PostgreSQL не требуются. Публичные интерфейсы health-report и WorkerManager не изменены.

### Проверки

Добавлен `tests/test_p2_final_stability_boundaries.py`. Полный GitHub Actions CI включает unit tests, Docker build и project notes contract.

### PR и commit

Ветка: `agent/close-final-p2-debts`. PR создаётся после подготовки инвентаря.

### Незавершённое

Внутри линии P2 unresolved broad catches и late/missing callbacks отсутствуют. Отдельными эксплуатационными задачами остаются staging, backup/restore drill и offsite backup, они не являются кодовыми долгами P2.

### Следующий шаг

Перейти от P2 code-stability backlog к эксплуатационной готовности: staging environment и независимая проверка восстановления backup.
