# P3D Core handler alias retirement

Дата: 2026-07-20

## Цель

Удалить завершившие миграцию compatibility aliases для core, owner, publication, system и watermark контроллеров после перевода оставшихся regression-тестов на canonical presentation imports.

## Удалённые aliases

- `velvet_bot.handlers.error_center`;
- `velvet_bot.handlers.owner_actions`;
- `velvet_bot.handlers.owner_menu`;
- `velvet_bot.handlers.publication_center`;
- `velvet_bot.handlers.publication_center_safe`;
- `velvet_bot.handlers.system_center`;
- `velvet_bot.handlers.watermark`.

## Canonical owners

- `velvet_bot.presentation.telegram.routers.core_operations_controllers.error_center`;
- `velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_actions`;
- `velvet_bot.presentation.telegram.routers.core_operations_controllers.owner_menu`;
- `velvet_bot.presentation.telegram.routers.core_operations_controllers.watermark`;
- `velvet_bot.presentation.telegram.routers.publication.center`;
- `velvet_bot.presentation.telegram.routers.publication.safe`;
- `velvet_bot.presentation.telegram.routers.system`.

## Изменения

- boundary и workflow tests импортируют canonical controllers напрямую;
- P3C contracts теперь проверяют отсутствие удалённых alias-файлов и владение обработчиками canonical-модулями;
- Supervisor aliases сохранены для отдельного следующего среза;
- backup alias сохранён для отдельного backup-среза;
- architecture inventory уменьшен с 25 до 18 aliases;
- handler consumer inventory уменьшен с 23 до 16 consumer-файлов и с 57 до 42 references;
- production Router composition и порядок регистрации routers не менялись;
- runtime compatibility components остаются 8;
- миграции базы данных не требуются.

## Проверяемые инварианты

- active legacy handler implementations: `0`;
- duplicate router registrations: `0`;
- production legacy imports: `0`;
- missing alias references: `0`;
- active routers: `58`;
- root-level Python modules: `117`.

## Не затрагивалось

Отложенный модуль `velvet_bot.presentation.telegram.routers.analytics_controllers.channel` и ошибка `Message.views` не изменялись.

## Следующий срез

P3D-Backup: перевести backup boundary-тесты на canonical module и удалить `velvet_bot.handlers.backup_center`. Затем P3D-Supervisor.
