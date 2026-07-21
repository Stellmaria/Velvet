# Сессия: P3E repository layout inventory

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-repository-layout-inventory`
- Линия/фаза: P3E repository and root-module layout
- Статус: `частично`
- Ветка: `agent/p3e-repository-layout-inventory`
- Базовый commit: `6c78064b9097e557398ad894e15de32ff18d4a20`

## Перед началом

### Цель

Построить машинный baseline неоднородного расположения repository-модулей, измерить их production/test consumers и выбрать первый низкосвязный модуль для отдельного P3E-переноса без изменения поведения.

### Исходный контекст

P3D завершён: `velvet_bot/handlers` содержит 0 implementations и 0 aliases, production legacy imports равны `0 / 0 / 0`. Следующий открытый долг находится в persistence layout: одновременно используются domain repositories, общий каталог `velvet_bot/repositories` и корневые `*_repository.py`. Корень `velvet_bot` содержит 117 Python-модулей, но точного consumer baseline для P3E пока нет.

### Планируемый объём

- добавить AST-инвентарь всех Python-модулей с `repository` в имени;
- классифицировать domain, central, root, infrastructure и прочие layouts;
- посчитать production/test consumers и references каждого repository-модуля;
- классифицировать корневые Python-модули по назначению;
- сформировать список низкосвязных кандидатов для первых P3E-срезов;
- зафиксировать JSON/Markdown baseline и CI contract;
- не переносить production-модули до получения измеримого результата discovery.

### Критерии готовности

- inventory воспроизводимо строится AST-сканером;
- generated JSON и Markdown совпадают с working tree;
- baseline содержит counts по layouts, root categories и consumer counts;
- выбран конкретный первый кандидат для следующего отдельного PR;
- handler aliases остаются 0;
- полный CI проходит.

### Риски и ограничения

Этот срез только измеряет структуру. Он не меняет imports, SQL, runtime composition, repository APIs или пользовательское поведение. Первый физический перенос выполняется отдельным PR после выбора кандидата по фактическому consumer count.

## После завершения

### Фактически сделано

Добавлен AST-сканер `scripts/inventory_repository_layout.py` и временный discovery-тест, который возвращает полный baseline через CI. Generated inventories и постоянный check будут добавлены после получения результата.

### Миграции и совместимость

Миграции базы данных не требуются. Import paths и runtime behavior на discovery-этапе не меняются.

### Проверки

Первый CI намеренно содержит discovery failure с сериализованным inventory. После фиксации baseline тест будет заменён постоянной проверкой generated JSON/Markdown и архитектурных инвариантов.

### PR и commit

PR создаётся из ветки `agent/p3e-repository-layout-inventory`; итоговый squash commit фиксируется после зелёного CI.

### Незавершённое

Требуется получить discovery output, создать `docs/repository_layout_inventory.json` и `.md`, заменить временный failing test на постоянный contract и выбрать первый P3E migration candidate.

### Следующий шаг

После зелёного inventory PR создать отдельный P3E-срез для первого низкосвязного root/central repository: новый canonical domain или infrastructure path, временный facade старого пути, миграция consumers и последующее удаление facade отдельным шагом.
