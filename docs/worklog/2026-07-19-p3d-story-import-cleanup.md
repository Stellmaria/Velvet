# Сессия: P3D очистка импортов story-router'ов

- Дата: 2026-07-19
- ID: `2026-07-19-p3d-story-import-cleanup`
- Линия/фаза: P3D, canonical import cleanup
- Статус: в работе
- Ветка: `agent/p3d-characters-stories-import-cleanup`
- Базовый commit: `ef93f01cc34ead12a2d292bcddeba13ceb4af024`

## Перед началом

### Цель

Убрать legacy-imports `velvet_bot.handlers.*` из двух связанных story-router'ов, не меняя callback-контракты и пользовательское поведение.

### Исходный контекст

После переноса реальных handler-реализаций каталог `velvet_bot.handlers` содержит compatibility aliases. Production-модули всё ещё импортируют через эти старые пути. В этом срезе затронуты `stories/universe_flow.py` и `stories/kr_universe_entry.py`, которые используют канонические реализации каталога персонажей, story management и multi-story KR через aliases.

### Планируемый объём

- заменить три legacy-imports на canonical presentation paths;
- сохранить имена callback classes и helper-функций;
- добавить regression/architecture contract для двух очищенных модулей;
- пройти tests, Docker build и project notes contract.

### Критерии готовности

- оба production-файла не содержат импортов `velvet_bot.handlers`;
- callback prefixes, router count и порядок routers не меняются;
- пользовательские сценарии назначения вселенной и истории остаются прежними;
- полный CI зелёный.

### Риски и ограничения

Срез не удаляет сами compatibility aliases и не очищает остальные consumers. Импорт `stories.management` из `stories.universe_flow` допустим, поскольку management не импортирует universe_flow и циклическая зависимость не создаётся. Следующие группы будут очищаться отдельными PR.

## После завершения

### Фактически сделано

Работа выполняется.

### Миграции и совместимость

Миграции не требуются. Callback data и Telegram UI не меняются.

### Проверки

Проверки ещё не запущены.

### PR и commit

PR будет создан после production-правок и regression-теста.

### Незавершённое

Остальные production consumers legacy handler paths остаются вне этого среза.

### Следующий шаг

Перевести два story-router'а на canonical imports и добавить точечный CI-контракт.