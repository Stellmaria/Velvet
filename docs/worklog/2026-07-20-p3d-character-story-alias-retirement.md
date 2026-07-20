# Сессия: P3D retirement character/story aliases

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-character-story-alias-retirement`
- Линия/фаза: Velvet Archive, P3D
- Статус: `завершено`
- Ветка: `agent/p3d-character-story-alias-retirement`
- Базовый commit: `06f8c4cdd29a70e82b93d3314e5a12559b5236fe`

## Перед началом

### Цель

Мигрировать character/story compatibility-тесты на canonical presentation modules и удалить девять старых handler aliases этой связанной группы.

### Исходный контекст

После PR #224 остаются 44 handler aliases, и все имеют repository references. Character/story aliases удерживаются только тестовыми imports, literal module paths и compatibility-проверкой P3C; production legacy-consumer baseline уже закрыт на `0 / 0 / 0`.

### Планируемый объём

- перевести character directory, uncategorized, stories и KR tests на canonical imports;
- заменить P3C alias-existence test проверкой canonical controllers и router composition;
- удалить девять character/story aliases после нулевого repository reference count;
- обновить alias, legacy и architecture inventories;
- не менять callbacks, команды, SQL и пользовательские тексты.

### Критерии готовности

- удалённые aliases не имеют repository references;
- callback classes продолжают импортироваться из публичных contracts;
- canonical controllers сохраняют router implementations и active composition order;
- production legacy-consumer baseline остаётся `0 / 0 / 0`;
- полный test suite, Docker build и project notes contract проходят.

### Риски и ограничения

Удаляется только группа, для которой все repository consumers переводятся в этом же срезе. Канонические controllers и callback payloads не меняются.

## После завершения

### Фактически сделано

- `test_admin_uncategorized`, `test_story_catalog`, topic-boundary, stability и owner-menu composition tests переведены на canonical presentation modules;
- P3C character/story test больше не проверяет существование legacy facades и вместо этого проверяет importability, router ownership и active canonical composition;
- удалены 9 aliases: `admin_directory`, `admin_stories`, `admin_uncategorized`, `admin_universe_story_flow`, `character_aliases`, `characters`, `kr_profile_overrides`, `kr_universe_entry`, `multi_story_kr`;
- handler alias count уменьшен с 44 до 35;
- все 35 оставшихся aliases имеют repository references;
- references на отсутствующие aliases: 0;
- production legacy-consumer baseline сохранён на `0 / 0 / 0`;
- документы и machine inventories синхронизированы.

### Миграции и совместимость

Миграции не требуются. `AdminDirectoryCallback` и `AdminStoryCallback` используются через публичные contracts. Callback prefixes, payload fields, router registration, команды, SQL и пользовательские тексты не изменены.

### Проверки

- character/story + inventory regression suite: 37 tests + 70 subtests, success;
- alias, legacy и architecture inventory checks: success;
- полный локальный suite: 923 tests, success; 24 PostgreSQL integration tests skipped без `TEST_DATABASE_URL`;
- финальные GitHub Actions фиксируются на head PR.

### PR и commit

- PR: создаётся после полного локального прогона;
- ветка: `agent/p3d-character-story-alias-retirement`;
- verified local tree готово к публикации отдельным squash PR.

### Незавершённое

Остаются 35 handler aliases, все с repository references, 8 runtime compatibility components, 114 root modules и неоднородное размещение repositories.

### Следующий шаг

Мигрировать следующую связанную alias-группу analytics/core либо quality. После сокращения compatibility-слоя перейти к P3E repository/root module layout и duplicate helper inventory.
