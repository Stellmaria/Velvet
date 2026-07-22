# Workspace team roles and custom watermark logos

- Дата: 2026-07-22
- ID: workspace-team-watermark
- Линия/фаза: Workspace product / team and branding
- Статус: частично
- Ветка: `agent/workspace-team-watermark`
- Базовый commit: `8a96569d6953b5e6d72779ade5a287c5b2eabeda`

## Перед началом

### Цель

Завершить крупный пользовательский блок канонического workspace ТЗ: дать владельцу личного архива безопасное управление командой и возможность использовать собственный логотип в watermark pipeline.

### Исходный контекст

Таблица `workspace_members` уже хранила роли owner/admin/editor/reviewer/viewer, но Telegram UI для списка, добавления, смены роли и удаления отсутствовал. Существующий Krita bridge применял только встроенный SVG Velvet Anatomy, а watermark job не знал workspace и не сохранял snapshot логотипа.

### Планируемый объём

- добавить доменный repository/service управления командой;
- реализовать Telegram UI списка участников и добавления по Telegram ID;
- разрешить owner назначать совладельца и администратора;
- ограничить admin ролями editor/reviewer/viewer;
- запретить саморедактирование через UI;
- защитить последнего owner PostgreSQL-trigger;
- хранить один активный SVG/PNG asset на workspace;
- очищать SVG от scripts, entities, event handlers и внешних ресурсов;
- требовать реальный alpha-канал у PNG/WebP;
- нормализовать raster в RGBA PNG;
- сохранять snapshot логотипа в каждом watermark job;
- передавать custom logo через Krita bridge schema v2;
- сохранить встроенный логотип для system workspace и старых вызовов;
- добавить contract, validation и PostgreSQL regression tests.

### Критерии готовности

- один workspace видит только своих участников и asset;
- owner может добавить owner/admin/editor/reviewer/viewer;
- admin не может назначить owner/admin или изменить owner/admin;
- последнего владельца нельзя удалить или понизить даже прямым SQL через repository;
- SVG со script, DOCTYPE, ENTITY или внешней ссылкой отклоняется;
- opaque PNG/WebP отклоняется;
- transparent PNG/WebP принимается и хранится как PNG;
- замена активного логотипа не изменяет старый watermark job;
- личный `/watermark` использует active workspace и enabled module;
- system watermark сохраняет встроенный Velvet logo;
- tests, type-check, Docker, notes и restore drill зелёные.

### Риски и ограничения

- Telegram обычно преобразует отправленное как фото изображение в JPEG и уничтожает alpha; прозрачный raster необходимо отправлять документом;
- SVG намеренно не поддерживает внешние шрифты, изображения и CSS imports;
- custom raster сохраняет собственные цвета, поэтому кнопки перекраски показываются только для встроенного логотипа;
- Krita должна быть обновлена вместе с bot-side bridge schema v2.

## После завершения

### Фактически сделано

- добавлена миграция `909_workspace_team_watermarks.sql`;
- `workspace_watermark_assets` хранит один активный asset на пространство;
- watermark jobs получили workspace ID и immutable logo snapshot;
- DB-trigger `protect_last_workspace_owner` закрывает удаление и понижение последнего владельца, но пропускает каскадное удаление самого workspace;
- `WorkspaceTeamRepository` и `WorkspaceTeamService` реализуют tenant и role policy;
- Telegram UI команды поддерживает список, добавление, смену роли и удаление;
- SVG проходит XML sanitization и не может использовать внешние ресурсы;
- PNG/WebP проверяется Pillow, требует прозрачные пиксели и нормализуется в PNG;
- asset хранится только внутри `KritaBridgePaths.assets`;
- workspace watermark UI поддерживает upload, replace, reset и запуск нового задания;
- Krita bridge schema v2 передаёт logo kind/path/dimensions/name;
- Krita plugin встраивает custom SVG или PNG в отдельный vector layer;
- legacy system workflow использует builtin logo по умолчанию;
- access policy получил guarded `wteam:`, `wlogo:` и `wm:` routes;
- compatibility callback допускает старый системный вызов без `WorkspaceService`;
- archive edit выполняет один owner-checked lookup и одинаково скрывает отсутствующее и чужое задание;
- тестовая очистка workspace использует продуктовый FK cascade вместо прямого удаления последнего owner;
- architecture, repository, Telegram navigation и P2 inventories пересобраны на финальном production tree.

### Миграции и совместимость

Добавлена миграция `909_workspace_team_watermarks.sql`. Старые `watermark_jobs` backfill-ятся в system workspace `1` и получают `logo_kind='builtin'`. Сигнатуры repository/service сохраняют default workspace `1`, поэтому прежние системные вызовы продолжают работать.

### Проверки

Добавлены тесты на:

- schema и last-owner trigger;
- порядок personal routers;
- access prefixes;
- bridge schema v2 и plugin custom logo support;
- transparent/opaque raster validation;
- safe/malicious SVG;
- owner/admin permission matrix;
- workspace-scoped membership list;
- workspace-scoped asset;
- immutable watermark job snapshot.

До финального connector-head отдельно подтверждены type-check, Docker build, project notes contract и backup restore drill. Последний чистый CI запущен после archive callback и workspace cleanup compatibility fixes.

### PR и commit

Draft PR: `#288 Add workspace team roles and custom watermark logos`. Production wiring, compatibility fixes и generated inventories находятся в ветке; финальный merge commit фиксируется после зелёного повторного CI.

### Незавершённое

- финальный PR CI и merge commit;
- tenant-aware Telegram export import остаётся отдельным следующим срезом.

### Следующий шаг

После зелёного CI перевести PR в ready и слить в `main`.
