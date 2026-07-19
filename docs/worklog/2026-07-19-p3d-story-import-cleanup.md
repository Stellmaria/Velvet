# Сессия: P3D очистка импортов story-router'ов

- Дата: 2026-07-19
- ID: `2026-07-19-p3d-story-import-cleanup`
- Линия/фаза: P3D, canonical import cleanup
- Статус: завершено
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

- `stories/universe_flow.py` переведён с `handlers.admin_directory` и `handlers.admin_stories` на canonical modules `characters.directory` и `stories.management`;
- `stories/kr_universe_entry.py` переведён с `handlers.admin_directory` и `handlers.multi_story_kr` на canonical modules `characters.directory` и `stories.multi_story_kr`;
- удалены три production legacy-imports;
- callback classes, prefixes, router registration, UI-тексты и ветвление обработчиков не менялись;
- добавлен AST regression contract `tests/test_p3d_story_canonical_imports.py`, который запрещает возвращение handler aliases в очищенные файлы и проверяет ожидаемые canonical dependencies;
- импортного цикла между `universe_flow` и `management` не возникло.

### Миграции и совместимость

Миграции не требуются. Callback data, Telegram UI, router count и compatibility alias-файлы не менялись. Внешние старые импорты продолжают работать через существующие aliases.

### Проверки

- tests #1075 выполнил 928 тестов: все production и regression-тесты прошли, единственный failure был ожидаемым project-notes assertion из-за статуса worklog `в работе`;
- Docker build #608: success;
- project notes contract #455: ожидаемый failure до финализации worklog;
- после этой записи запускается повторный полный CI финального documentation head.

### PR и commit

- PR: #217 `P3D: clean canonical imports in story routers`;
- `universe_flow` canonical imports: `6e535afcab1a64ca5dd9ee47f314c63cde49fae6`;
- `kr_universe_entry` canonical imports: `77872b7498958c9a90c17d84b4741fd1c176e72f`;
- regression contract: `df232fb0452bdfae526271e3ec9ea3e4bf22ab67`.

### Незавершённое

Остальные production consumers legacy handler paths остаются вне этого среза. Сами compatibility alias-файлы также пока не удаляются.

### Следующий шаг

После зелёного повторного CI слить PR #217. Следующим отдельным срезом очистить `characters/uncategorized.py` и `stories/management.py` от `handlers.admin_directory`.