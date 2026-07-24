# Сессия: persistence boundary черновиков watermark

- Дата: 2026-07-24
- ID: `2026-07-24-watermark-draft-persistence-boundary`
- Линия/фаза: workspace architecture cleanup
- Статус: `частично`
- Ветка: `agent/watermark-draft-persistence-boundary`
- Базовый commit: `c29499bccdb6c9de358bb0eb6c240ab1fb07a506`

## Перед началом

### Цель

Перенести создание, изменение, undo и постановку в очередь draft watermark revisions из Telegram controller в `WatermarkRepository` и нативный `WatermarkService`.

### Исходный контекст

`workspace_product_experience.py` напрямую выполнял SQL для `watermark_jobs` и `watermark_revisions`, обращался к `repository._database`, `_map_job`, `_map_revision`, `_settings_from_row`, `_current_query` и во время установки подменял методы `WatermarkService`.

### Планируемый объём

- сделать status новой revision явным параметром repository;
- добавить repository-операцию перевода draft/error revision в pending;
- добавить нативные draft-aware методы service;
- передавать workspace template и draft mode из core watermark flow;
- удалить persistence SQL и service monkeypatch из workspace controller;
- добавить unit, architecture и PostgreSQL integration coverage.

### Критерии готовности

- controller не содержит SQL watermark persistence и private repository access;
- `WatermarkService` не подменяется во время runtime installation;
- draft revision не захватывается worker до явной генерации;
- после генерации revision становится pending и доступна worker;
- полный CI зелёный.

### Риски и ограничения

UI formatter/keyboard и `_wake_krita` runtime patch пока не удаляются. Их перенос является отдельным presentation/runtime срезом. Схема БД не меняется.

## После завершения

### Фактически сделано

- подготовлены domain и presentation transformations;
- добавлены service и architecture regression-тесты;
- подготовлен integration test жизненного цикла draft → pending → processing.

### Миграции и совместимость

Новые миграции не требуются. Существующие статусы `draft`, `pending`, `processing`, `ready`, `error` и текущие callback data сохраняются.

### Проверки

Результаты focused и полного CI будут записаны после применения transformations.

### PR и commit

Ветка `agent/watermark-draft-persistence-boundary`; PR создаётся после применения и focused validation.

### Незавершённое

- применить transformations;
- выполнить focused tests;
- открыть PR и дождаться полного CI.

### Следующий шаг

После merge вынести watermark UI formatter/keyboard и Krita wake policy из runtime installer в явные presentation contracts.
