# Сессия: классификация оставшихся handler implementations

- Дата: 2026-07-19
- ID: `2026-07-19-p3d-residual-handler-classification`
- Линия/фаза: Velvet Archive, P3D
- Статус: `завершено`
- Ветка: `agent/p3d-residual-handler-classification`
- Базовый commit: `64d318bc2cd30556faa7f01a1e821ba7b844f3c8`

## Перед началом

### Цель

Определить и классифицировать пять последних физических implementations в `velvet_bot/handlers`, после того как все четыре domain bundles перешли на canonical presentation controllers.

### Исходный контекст

P3C завершён: root Router и domain bundles не импортируют `velvet_bot.handlers.*`, активных bundle routers 56, дублирующих регистраций 0. В handlers оставались 68 файлов, из которых 63 являлись module aliases, а пять всё ещё содержали реальный код. Поисковый индекс GitHub показывал старые версии файлов, поэтому остаток определялся непосредственно текущим деревом в CI.

### Планируемый объём

- добавить машинный контракт остаточных implementations;
- получить точный набор имён из текущего checkout;
- классифицировать каждый файл как active nested controller, служебный module или устаревший остаток;
- перенести active controllers в presentation;
- удалить либо оставить с явным назначением не-router modules;
- не менять пользовательские функции, команды, callbacks и бизнес-логику;
- обновить architecture inventory и следующий P3D-срез.

### Критерии готовности

- набор пяти файлов явно записан и защищён тестом;
- каждый файл имеет подтверждённого runtime owner;
- скрытые imports из canonical controllers найдены;
- active controllers перенесены с module identity compatibility;
- legacy implementation count уменьшается до фактического минимального значения;
- tests, Docker build и project notes contract зелёные.

### Риски и ограничения

`watermark.py` является большим nested controller с файловым и Krita workflow. Его перенос выполнялся без переписывания исходного blob и с сохранением порядка inclusion в owner menu. Четыре analytics management helper-модуля являются частью canonical analytics controller, хотя сами не объявляют отдельные routers.

## После завершения

### Фактически сделано

- discovery CI #1042 подтвердил точный residual set: `watermark.py`, `analytics_management_common.py`, `analytics_management_tags.py`, `analytics_management_aliases.py`, `analytics_management_publications.py`;
- `watermark.py` перенесён в `core_operations_controllers/watermark.py`;
- четыре analytics helper-модуля перенесены в `analytics_controllers/management_*`;
- runtime owners `owner_menu.py`, `management.py` и `dashboard_overrides.py` переключены на canonical imports;
- пять legacy handler-файлов заменены module aliases;
- discovery sentinel заменён постоянным контрактом нулевого остатка и module identity;
- Phase 14, P3C analytics и P3C core contracts переведены на canonical paths;
- architecture inventory обновлён: 68 handler files, 0 implementations, 68 aliases;
- следующим P3D-срезом назначено controlled compatibility alias retirement.

### Миграции и совместимость

Миграции PostgreSQL не требуются. Команда `/watermark`, Watermark callbacks, Krita bridge, analytics management actions, alias ForceReply, publication review и unresolved hashtag flows не изменены. Старые imports продолжают возвращать те же canonical module objects.

### Проверки

- discovery run: tests #1042 завершился единственным ожидаемым failure sentinel и напечатал точный набор пяти файлов; остальные 900 тестов прошли;
- runtime/finalized tree: tests #1051 — success, 901 tests;
- Docker build #586 — success;
- project notes contract #437 — success;
- active bundle routers: 56;
- duplicate registrations: 0;
- active legacy implementations: 0;
- handler aliases: 68.

### PR и commit

- PR: #210 `Classify residual handler implementations`;
- рабочая ветка: `agent/p3d-residual-handler-classification`;
- discovery contract commit: `bb019b885f5208205b4f9a7a2e72c5a08e7aaa18`;
- residual move commit: `0627e496f3e97f3dd5b3e90b264e3cd98d3976b9`;
- проверенный runtime head: `e52cc2460d01dc9356292fba4c77a84f6dbc2668`.

### Незавершённое

Реальных implementations в `velvet_bot/handlers` больше нет. Остаются 68 временных module aliases. Их нельзя удалять одним массовым commit, пока tests, compatibility modules или внешние scripts могут импортировать старые paths.

### Следующий шаг

Слить PR #210 после зелёного CI финального documentation head. Затем начать P3D compatibility retirement: найти consumers старых paths, перевести их на canonical imports и удалять aliases небольшими проверяемыми группами.
