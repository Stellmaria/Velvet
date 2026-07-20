# Сессия: удаление P3D Core handler aliases

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-core-alias-retirement`
- Линия/фаза: P3D Core compatibility alias retirement
- Статус: `завершено`
- Ветка: `agent/p3d-core-alias-retirement`
- Базовый commit: `6a8dc298098a94490d23efad025e9a1b8146f2ee`

## Перед началом

### Цель

Удалить завершившие миграцию compatibility aliases для core, owner, publication, system и watermark контроллеров после перевода оставшихся regression- и boundary-тестов на canonical presentation imports.

### Исходный контекст

После P3D-Q в `velvet_bot/handlers` оставалось 25 module aliases при нулевом количестве production legacy imports и нулевом количестве активных handler implementations. Core, owner, publication, system и watermark runtime уже использовали canonical presentation-модули, но старые тесты продолжали импортировать семь compatibility paths и тем самым удерживали aliases в репозитории.

### Планируемый объём

- перевести оставшиеся tests на canonical modules;
- заменить старые alias-contract tests проверками отсутствия удалённых файлов;
- удалить семь core/publication/system aliases;
- сохранить Supervisor и backup aliases для отдельных срезов;
- обновить architecture и handler consumer inventories;
- не менять Router composition, callback contracts и runtime behavior.

### Критерии готовности

- семь выбранных alias-файлов отсутствуют;
- canonical controllers остаются владельцами router implementations;
- production legacy imports и missing alias references равны нулю;
- количество aliases уменьшается с 25 до 18;
- количество consumer-файлов уменьшается с 23 до 16;
- полный CI, Docker build и project notes contract проходят.

### Риски и ограничения

Удаление aliases допустимо только после перевода всех test consumers. Полные dotted names удалённых модулей нельзя оставлять даже в строковых test fixtures, потому что машинный inventory трактует их как ссылки на отсутствующие aliases. Backup и Supervisor не смешиваются с этим срезом из-за отдельных runtime и recovery-контрактов. Отложенный channel analytics controller не затрагивается.

## После завершения

### Фактически сделано

- tests владельца, Error Center, публикаций и System Center переведены на canonical imports;
- P3C core/publication/system contracts проверяют отсутствие удалённых файлов и наличие реализаций в canonical modules;
- удалены `error_center`, `owner_actions`, `owner_menu`, `publication_center`, `publication_center_safe`, `system_center` и `watermark` aliases;
- architecture inventory обновлён до 18 aliases, 58 active routers и 117 root-level modules;
- handler consumer inventory обновлён до 16 consumer-файлов и 42 references;
- Supervisor aliases, backup alias и 8 runtime compatibility components сохранены без изменений;
- production Router composition и порядок регистрации routers не менялись.

### Миграции и совместимость

SQL-миграции не требуются. Telegram callback-data, команды, owner menu, публикации, Error Center, watermark и System Center сохраняют прежнее поведение. Удаляются только временные import paths, которые больше не используются production-кодом.

### Проверки

Обновлены architecture inventory contracts, handler consumer inventory contracts, P3C controller tests и профильные boundary/workflow tests. Полный GitHub CI запускается в PR #232.

### PR и commit

PR #232 создан из ветки `agent/p3d-core-alias-retirement`. Итоговый merge commit фиксируется после зелёных tests, Docker build и project notes contract.

### Незавершённое

Остаются 18 aliases: восемь analytics management/dashboard aliases, `channel_analytics`, `backup_center` и восемь Supervisor aliases. Также остаются 8 runtime compatibility components и 117 корневых Python-модулей.

### Следующий шаг

Выполнить P3D-Backup: перевести backup tests на canonical controller и удалить `velvet_bot.handlers.backup_center`. После этого отдельным срезом удалить восемь Supervisor aliases. Отложенный `analytics_controllers.channel` и ошибка `Message.views` остаются без изменений.
