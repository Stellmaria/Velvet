# Сессия: P3E repository layout inventory

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-repository-layout-inventory`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-repository-layout-inventory`
- Базовый commit: `6c78064b9097e557398ad894e15de32ff18d4a20`

## Перед началом

### Цель

Построить машинный baseline неоднородного расположения repository-модулей, измерить их production/test consumers и выбрать первый низкосвязный модуль для отдельного P3E-переноса без изменения поведения.

### Исходный контекст

P3D завершён: `velvet_bot/handlers` содержит 0 implementations и 0 aliases, production legacy imports равны `0 / 0 / 0`. Следующий открытый долг находится в persistence layout: одновременно используются domain repositories, общий каталог `velvet_bot/repositories` и корневые `*_repository.py`. Корень `velvet_bot` содержит 117 Python-модулей, но точного consumer baseline для P3E не было.

### Планируемый объём

- добавить AST-инвентарь всех Python-модулей с `repository` в имени;
- классифицировать domain, central, root, infrastructure и прочие layouts;
- отдельно посчитать production consumers, tests, package exports и references;
- классифицировать корневые Python-модули по назначению;
- сформировать список низкосвязных кандидатов для первых P3E-срезов;
- зафиксировать JSON/Markdown baseline и CI contract;
- не переносить production-модули до получения измеримого результата discovery.

### Критерии готовности

- inventory воспроизводимо строится AST-сканером;
- generated JSON и Markdown совпадают с working tree;
- baseline содержит counts по layouts, root categories и consumer scopes;
- выбран конкретный первый кандидат для следующего отдельного PR;
- handler aliases остаются 0;
- полный CI проходит.

### Риски и ограничения

Этот срез только измеряет структуру. Он не меняет imports, SQL, runtime composition, repository APIs или пользовательское поведение. Первый физический перенос выполняется отдельным PR после выбора кандидата по фактическому consumer count.

## После завершения

### Фактически сделано

- добавлен AST-сканер `scripts/inventory_repository_layout.py`;
- учтены абсолютные, относительные и package-level imports, включая `__init__.py` re-exports;
- package exports отделены от реальных runtime consumers;
- зафиксирован baseline: 33 repository-модуля, из них 23 domain, 3 central и 7 root;
- infrastructure/other repository paths сейчас равны 0;
- 29 модулей имеют production consumers, 24 экспортируются через package `__init__`, 4 не имеют runtime consumers;
- export-only модули: `velvet_bot.repositories.public_notification_repository` и `velvet_bot.domains.media_rework.repository`;
- корневые 117 модулей классифицированы: 7 repositories, 4 reports, 4 runtimes, 1 service, 1 worker и 100 other;
- создан generated baseline `docs/repository_layout_inventory.json` и `.md`;
- временный discovery failure заменён постоянным regression contract;
- первым следующим кандидатом выбран `velvet_bot.repositories.public_notification_repository`.

### Миграции и совместимость

Миграции базы данных не требуются. Production import paths и runtime behavior в этом срезе не изменялись. Inventory только наблюдает структуру и блокирует незадокументированный drift generated baseline.

### Проверки

Проверяются точное совпадение AST inventory с generated JSON/Markdown, разделение package exports и runtime consumers, layout counts и измеримый следующий кандидат. Полный GitHub CI запускается в PR №250.

### PR и commit

PR №250 создан из ветки `agent/p3e-repository-layout-inventory`; итоговый squash commit фиксируется после зелёного CI.

### Незавершённое

Repository layout ещё не нормализован. Остаются 3 central repositories, 7 корневых repositories и 100 неклассифицированных корневых модулей. Два repository-модуля существуют только как package exports и требуют отдельного проверяемого retirement-среза.

### Следующий шаг

Отдельным P3E-срезом удалить export-only `velvet_bot.repositories.public_notification_repository`: убрать его из `velvet_bot/repositories/__init__.py`, удалить мёртвый модуль, обновить inventory и подтвердить отсутствие hidden/dynamic consumers. После этого перейти к `publication_repository` либо первому root media-set repository по новому baseline.
