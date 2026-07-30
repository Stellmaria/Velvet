# 2026-07-30 — реестр runtime compatibility-компонентов

- Дата: 2026-07-30
- ID: `runtime-compatibility-contracts`
- Линия/фаза: P3 / root modules and compatibility retirement
- Статус: `частично`
- Ветка: `agent/p3-runtime-compatibility-contracts`
- Базовый commit: `e24fae5f4a7b36ff2192be42807ccc227964156e`

## Перед началом

### Цель
Зафиксировать для каждого из восьми активных runtime compatibility-компонентов владельца, consumers, side effect и конечное архитектурное решение, чтобы дальнейшее удаление выполнялось измеримыми PR, а новые неописанные monkeypatch-слои блокировались тестом.

### Исходный контекст
`velvet_bot/presentation/telegram/compat.py` перечислял семь pre-import и один post-import component, но реестр содержал только имена и порядок установки. Причина существования, фактические consumers и целевая замена оставались распределены по root modules и комментариям.

### Планируемый объём
- создать типизированный compatibility contract registry;
- описать все восемь активных компонентов;
- выбрать решение permanent/explicit/remove для каждого;
- добавить человекочитаемый inventory;
- закрепить полноту registry regression-тестом;
- не менять runtime behavior в этом срезе.

### Критерии готовности
- активные компоненты и contracts совпадают один к одному;
- для каждого заполнены stage, owner, consumers, side effect и replacement;
- ни один активный monkeypatch не считается постоянным без явного решения;
- тест падает при добавлении компонента только в `compat.py` либо только в registry;
- полный CI проходит.

### Риски и ограничения
Этот PR не удаляет installers и не переносит consumers. Смешивание inventory с восемью behavioral migrations сделало бы review бессмысленным и повысило риск нарушения import order. Root-module classification выполняется следующим отдельным срезом issue #418.

## После завершения

### Фактически сделано
- добавлен `runtime_contracts.py` с восемью типизированными contracts;
- все компоненты получили решение `remove-after-consumer-migration`;
- зафиксированы owner modules, consumers, runtime side effects и canonical replacements;
- добавлен `docs/runtime_compatibility_inventory.md` с порядком retirement;
- добавлен contract test на полноту, stage ordering и синхронизацию документации;
- registry назван без `compat` в имени, чтобы справочный модуль не увеличивал счётчик активного compatibility-долга.

### Миграции и совместимость
SQL, callbacks, FSM и runtime installation order не менялись. `compat.py` остаётся действующей границей, поэтому текущий production behavior сохраняется полностью.

### Проверки
- новый unit contract проверяет совпадение registry с literal `PRE_IMPORT_COMPONENTS` и `POST_IMPORT_COMPONENTS` без запуска installers;
- первый tests workflow выявил только устаревшие generated inventories после добавления Python-файла;
- Telegram navigation и architecture layout inventories пересобраны;
- итоговый CI повторно запускает full tests, type check, Docker build и project notes contract.

### PR и commit
- issue: #418;
- PR: #449;
- branch: `agent/p3-runtime-compatibility-contracts`;
- current head после исправления inventories фиксируется GitHub;
- ключевые commits: `afd00d4f65d2f0e51a93578423b41271c07b0d3d`, `bff0e5ebc05353cae3d32baa184df5a15b6507b8`, `1395f4c3713dff9eb511bc04ac8ae534e44b6085`.

### Незавершённое
- пересборка и классификация root-module inventory;
- фактическая миграция consumers;
- удаление восьми installers отдельными regression-protected PR;
- обновление umbrella #213 после завершения всего issue #418.

### Следующий шаг
После зелёного CI слить inventory-срез, затем первым behavioral PR удалить `ai-quality-schema`: перенести deployed media schema непосредственно в `AIQualityRepository`, удалить installer и закрепить SQL/mapping regression-тестом.
