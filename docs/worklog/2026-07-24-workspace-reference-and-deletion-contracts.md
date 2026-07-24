# Сессия: workspace reference dashboard and deletion contracts

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-reference-and-deletion-contracts`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/remove-dead-workspace-owner-views`
- Базовый commit: `717b7694b1913624599a7aaf8956ba7b87d19e83`

## Перед началом

### Цель

Продолжить уменьшение runtime-ответственности `workspace_owner_controls.py`: вывести reference dashboard и полное удаление workspace в явные публичные presentation/controller contracts перед физической зачисткой исторического файла.

### Исходный контекст

После PR #320 и #321 archive dashboard и role-aware home уже перехватывались bundle-level обработчиками. В `workspace_owner_controls.py` оставались живыми reference dashboard, открытие коллекции референсов, команда удаления пространства и callbacks подтверждения, отмены и завершения удаления.

### Планируемый объём

- создать типизированный reference dashboard contract;
- перенести module entry и `wref` callback flow в отдельный controller;
- перенести confirmation keyboard, транзакционное удаление и callbacks workspace deletion;
- регистрировать новые обработчики на bundle-уровне раньше legacy owner router;
- перевести отмену удаления на canonical workspace home presentation;
- добавить functional и architecture regressions;
- обновить Telegram navigation inventory.

### Критерии готовности

- reference dashboard сам владеет SQL, view-моделью, callback prefix и клавиатурой;
- reference module entry и открытие коллекции не зависят от `workspace_owner_controls`;
- удаление workspace использует отдельный транзакционный controller;
- отмена удаления возвращает canonical role-aware home;
- bundle-level registrations расположены раньше `workspace_owner_controls_router`;
- callback data, тексты, role checks и SQL-семантика сохранены;
- navigation inventory не содержит violations.

### Риски и ограничения

Исторические реализации пока физически остаются в `workspace_owner_controls.py`, но после регистрации новых bundle-level handlers не участвуют в соответствующих runtime flows. Физическое удаление остаётся отдельным механическим срезом после вывода живых обязанностей.

## После завершения

### Фактически сделано

- добавлен `workspace_reference_dashboard.py` с immutable character/dashboard моделями;
- SQL-загрузка, `wref` callback data и keyboard builder вынесены в публичный contract;
- добавлен `workspace_reference_dashboard_controller.py` для module entry, help и открытия коллекции;
- добавлен `workspace_deletion_controller.py` с confirmation UI, owner checks и транзакционным удалением;
- cancel flow использует `build_workspace_home_presentation` и восстанавливает scoped commands;
- reference и deletion registrars подключены раньше broad owner-controls router;
- добавлены functional и source-level architecture regressions;
- Telegram navigation inventory обновлён до 446 Python-файлов и 839 inline-кнопок без violations.

### Миграции и совместимость

Миграции не требуются. Сохранены callback prefixes `wsp` и `wref`, команда `/workspace_delete`, viewer/owner проверки, тексты подтверждения, SQL-порядок удаления и стартовая клавиатура после завершения.

### Проверки

- reference dashboard functional tests добавлены;
- deletion keyboard и architecture boundary tests добавлены;
- project notes contract, type check, полный test suite и Docker build выполняются в PR CI.

### PR и commit

- ветка: `agent/remove-dead-workspace-owner-views`;
- PR создаётся после финального сравнения с `main`.

### Незавершённое

Функциональных незавершённых пунктов в рамках среза нет. Дублирующие legacy home/archive/reference/deletion blocks остаются физически внутри `workspace_owner_controls.py`, но canonical bundle-level handlers перехватывают их callback и command входы.

### Следующий шаг

Физически удалить недостижимые home, archive dashboard, reference dashboard и workspace deletion blocks из `workspace_owner_controls.py`, затем разделить оставшийся personal archive media controller на navigation, policy и mutation части.
