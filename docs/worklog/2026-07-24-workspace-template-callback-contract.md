# Сессия: canonical callback contract шаблонов watermark

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-template-callback-contract`
- Линия/фаза: workspace architecture cleanup
- Статус: `частично`
- Ветка: `agent/workspace-template-callback-contract`
- Базовый commit: `154b54bab50f0e0259ec609a1800a55d4a0fbbd2`

## Перед началом

### Цель

Перенести поддержку callback prefix `wmtpl:` из runtime monkeypatch workspace installer в канонический access classifier.

### Исходный контекст

`workspace_product_experience.py` сохранял оригинальную функцию `is_workspace_member_callback_data`, оборачивал её для одного дополнительного prefix и во время установки подменял функцию в middleware module. Корректность доступа зависела от порядка импортов и вызова installer.

### Планируемый объём

- добавить `wmtpl:` в canonical `WORKSPACE_MEMBER_CALLBACK_PREFIXES`;
- удалить wrapper, сохранённый original alias и mutation middleware function;
- перевести существующий тест на публичный core access contract;
- добавить architecture regression-test запрета monkeypatch.

### Критерии готовности

- `wmtpl:` распознаётся без импорта workspace installer;
- неизвестные prefix не получают workspace access;
- controller не импортирует и не подменяет access middleware;
- focused и полный CI зелёные.

### Риски и ограничения

Проверка активного workspace, роли и tenant ownership остаётся в middleware и целевых handlers. Этот срез меняет только классификацию уже существующего callback prefix.

## После завершения

### Фактически сделано

- подготовлен canonical prefix contract;
- подготовлено удаление access monkeypatch;
- добавлены functional и architecture regression-тесты.

### Миграции и совместимость

Миграции не требуются. Формат callback data `wmtpl:*` не меняется.

### Проверки

Результаты будут записаны после применения checked transformation.

### PR и commit

Ветка `agent/workspace-template-callback-contract`; PR создаётся после focused validation.

### Незавершённое

- применить transformation;
- выполнить focused и полный CI;
- слить отдельный PR.

### Следующий шаг

Перенести quick references keyboard extension из runtime installer в canonical workspace keyboard contract.
