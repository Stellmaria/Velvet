# Сессия: перенос core operations controllers в presentation

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-core-operations-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `частично`
- Ветка: `agent/p3c-core-operations-controllers`
- Базовый commit: `f8898970ced75d561914e044c6041c2d0b2739cc`

## Перед началом

### Цель

Перенести оставшиеся прямые legacy Telegram-контроллеры bundle `core_operations` из `velvet_bot/handlers` в канонический presentation-пакет без изменения команд, callback contracts, порядка регистрации и пользовательского поведения.

### Исходный контекст

После слияния PR #202 analytics bundle полностью перешёл на canonical controllers. В `core_operations.py` оставались три прямых legacy imports: `error_center`, `owner_actions` и `owner_menu`. Supervisor и System уже были перенесены ранее и не требовали повторной обработки.

### Планируемый объём

- создать canonical пакет `presentation/telegram/routers/core_operations_controllers/`;
- перенести `error_center`, `owner_actions` и `owner_menu` без функциональных изменений;
- заменить старые handler-файлы module aliases того же объекта;
- переключить `core_operations` bundle на canonical imports в прежнем порядке;
- сохранить команды `/test_error_alert`, `/menu` и `/admin`;
- сохранить error callback data `err:ack:*`, `err:ackall`, `OwnerActionCallback` и `OwnerMenuCallback`;
- сохранить включение watermark router внутри owner menu;
- обновить P3 router contract и architecture inventory;
- добавить regression-тесты module identity, canonical ownership и bundle composition;
- не менять application services, Telegram forms, тексты, SQL и миграции.

### Критерии готовности

- canonical modules содержат реальные implementations;
- legacy imports возвращают те же module objects и не содержат router decorators;
- `core_operations` bundle содержит пять routers в прежнем порядке;
- команды, callback schemas и owner reply marker `OWNER_ACTION:*` сохранены;
- active legacy implementations уменьшаются с 30 до 27;
- aliases увеличиваются с 38 до 41;
- полный tests, Docker build и project notes contract зелёные.

### Риски и ограничения

`owner_menu` включает `watermark_router` из отдельного legacy handler. Watermark является вложенным крупным контроллером со своей Krita boundary, файлами и callback workflow, но не прямым import bundle `core_operations`. Его перенос намеренно не смешивается с текущим срезом: это потребовало бы отдельной проверки image processing и supervisor integration. Legacy module aliases сохраняются для monkeypatch и обратной совместимости до P3D.

## После завершения

### Фактически сделано

- создан пакет `velvet_bot/presentation/telegram/routers/core_operations_controllers`;
- три implementations перенесены через повторное использование исходных Git blob SHA без переписывания кода;
- `error_center`, `owner_actions` и `owner_menu` в legacy handlers заменены module aliases;
- `core_operations.py` переключён на canonical imports с прежним include order;
- P3 router contract направлен на canonical paths;
- добавлен `tests/test_p3c_core_operations_controllers.py`;
- architecture inventory обновлён до 27 implementations и 41 alias;
- следующим P3C-срезом назначены quality operations presentation controllers.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. Команды `/test_error_alert`, `/menu`, `/admin`, owner forms, callback data, reply marker `OWNER_ACTION:*`, порядок routers и включение watermark router сохранены. Старые import paths возвращают те же canonical module objects.

### Проверки

- architecture inventory подготовлен: root handler imports 0, active routers 56, duplicates 0, implementations 27, aliases 41;
- source-level и module-identity regression contracts добавлены;
- полный CI будет зафиксирован после создания PR.

### PR и commit

- рабочая ветка: `agent/p3c-core-operations-controllers`;
- runtime move commit: `f90c44089ccbefa5c41109b0c5a4ebeebcc94392`;
- основной PR будет создан после фиксации worklog;
- финальный head и CI runs будут добавлены после проверки.

### Незавершённое

До зелёного полного CI срез считается частично завершённым. `watermark.py` остаётся активным legacy controller внутри owner menu и требует отдельного переноса с проверкой Krita workflow. Временные aliases остаются контролируемым остатком P3D.

### Следующий шаг

Создать PR, пройти полный CI, зафиксировать результаты в worklog и после слияния начать P3C перенос quality operations presentation controllers.
