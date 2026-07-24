# Сессия: boundary настроек подсказок workspace

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-hint-preference-boundary`
- Линия/фаза: workspace architecture cleanup
- Статус: `частично`
- Ветка: `agent/workspace-hint-preference-boundary`
- Базовый commit: `e3a0d46505706c5131d4efab5c529375e4ce6ca0`

## Перед началом

### Цель

Убрать SQL и приватный доступ к repository internals для настройки видимости подсказок из Telegram controller.

### Исходный контекст

`workspace_product_experience.py` напрямую читал и обновлял `workspace_settings.show_button_hints`, доставал Database через `workspace_product_service._workspaces._database` и читал настройки через приватный `_workspaces`.

### Планируемый объём

- добавить методы чтения и переключения подсказок в `WorkspaceProductRepository`;
- открыть transport-neutral операции через `WorkspaceProductService`;
- перевести Telegram controller на публичный service contract;
- запретить возврат SQL и private repository access regression-тестом.

### Критерии готовности

- в Telegram controller нет SQL для `show_button_hints`;
- controller не обращается к `_workspaces` и не извлекает Database из service;
- repository/service tests проходят;
- полный CI зелёный.

### Риски и ограничения

Поведение кнопки и значение по умолчанию должны сохраниться. Этот срез не переносит watermark draft SQL и не удаляет runtime patch installer.

## После завершения

### Фактически сделано

- подготовлены repository/service методы для hint preference;
- подготовлен перевод controller на публичный service contract;
- добавлены unit- и architecture regression-тесты.

### Миграции и совместимость

Новые миграции не требуются. Существующий столбец `workspace_settings.show_button_hints` и callback data сохраняются.

### Проверки

Focused и полный CI будут зафиксированы после применения code transformation.

### PR и commit

Ветка `agent/workspace-hint-preference-boundary`; PR создаётся после применения и focused validation.

### Незавершённое

- применить transformations;
- выполнить focused tests;
- открыть PR и дождаться полного CI.

### Следующий шаг

После этого среза перенести watermark draft SQL и mapping из Telegram controller в `WatermarkRepository`.
