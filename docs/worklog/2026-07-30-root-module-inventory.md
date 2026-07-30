# 2026-07-30 — классификация корневых модулей

- Дата: 2026-07-30
- ID: `root-module-inventory`
- Линия/фаза: P3 / issue #418
- Статус: `завершено`
- Ветка: `agent/close-root-module-inventory-v2`
- Базовый commit: `dc96096934c6094cd66e4b782fd829479f2ca73d`

## Перед началом

### Цель

Завершить issue #418: классифицировать все `velvet_bot/*.py`, определить их consumers и import-time side effects, оставить public facade только при явном контракте и запретить появление новых необоснованных root modules.

### Исходный контекст

PR #449 уже зафиксировал contracts для восьми активных runtime compatibility-компонентов и выбрал для каждого путь `remove-after-consumer-migration`. Оставшейся частью issue была полная классификация 113 исторических root modules и машинный запрет на дальнейшее разрастание корня.

### Планируемый объём

- добавить AST-инвентаризацию root modules;
- присвоить каждому одну из шести категорий;
- собрать repository consumers;
- выявить import-time calls, assignments и control flow;
- зафиксировать public facade contracts;
- добавить baseline count и hash имён;
- закрепить результат regression-тестом и документацией.

### Критерии готовности

- inventory содержит все текущие root modules;
- `unclassified_count` равен нулю;
- новые или переименованные root modules ломают CI до явного обновления baseline;
- каждый public facade имеет текстовый контракт;
- tests, type check, Docker build и project notes contract проходят;
- issue #418 и соответствующий пункт umbrella #213 закрываются после merge.

### Риски и ограничения

Этот срез классифицирует физическую структуру и описывает side effects, но не переносит сразу десятки модулей и не удаляет восемь runtime installers одним изменением. Behavioral retirement выполняется отдельными малыми PR, иначе архитектурная уборка снова превратится в неразбираемый общий ремонт.

## После завершения

### Фактически сделано

- добавлен `scripts/inventory_root_modules.py`;
- каждый root module получает категорию, classification rule, consumers и side effects;
- public facade ограничены явным allowlist с описанием контракта;
- состав root modules защищён count и SHA-256 baseline;
- добавлен `tests/test_root_module_inventory.py`;
- добавлен человекочитаемый `docs/root_module_inventory.md`.

### Миграции и совместимость

SQL, callbacks, FSM, runtime imports и пользовательское поведение не меняются. Inventory только измеряет существующую структуру и блокирует несанкционированное расширение корневого слоя.

### Проверки

- первая CI-проверка используется для фиксации фактического hash и распределения категорий;
- после синхронизации baseline запускаются полный tests workflow, type check, Docker build и project notes contract;
- generated Telegram navigation inventory обновляется из-за добавления Python-файлов.

### PR и commit

- issue: #418;
- branch: `agent/close-root-module-inventory-v2`;
- PR создаётся после фиксации машинного baseline;
- начальный commit inventory фиксируется GitHub.

### Незавершённое

В рамках #418 незавершённых классификационных пунктов после зелёного CI не остаётся. Фактический перенос отдельных root modules и retirement runtime compatibility-компонентов продолжаются самостоятельными архитектурными PR согласно уже зафиксированным contracts.

### Следующий шаг

После merge закрыть #418 как completed, отметить его выполненным в #213 и продолжить первый behavioral retirement `ai-quality-schema` отдельным изменением с собственным regression test.
