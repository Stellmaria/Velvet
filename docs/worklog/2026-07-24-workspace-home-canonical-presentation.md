# Сессия: canonical workspace home presentation

- Дата: 2026-07-24
- ID: `2026-07-24-workspace-home-canonical-presentation`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/workspace-home-presentation-contract`
- Базовый commit: `f01a5883d1c93efb23c004e638874a58dc66e38e`

## Перед началом

### Цель

Опубликовать единый role-aware presentation contract для домашнего экрана пространства и сделать его фактическим runtime-входом `wsp:home`, не сохраняя зависимость новых контроллеров от private `_workspace_home_keyboard`, `_render_home` и `_render_member_home`.

### Исходный контекст

После canonical archive dashboard основная кнопка возврата в пространство всё ещё попадала в большой `workspace_owner_controls.py`. Владелец, участник и переключатель подсказок собирали близкие варианты home-панели в разных местах, а тесты импортировали private keyboard helper напрямую.

### Планируемый объём

- добавить immutable home presentation view-модель;
- опубликовать owner keyboard builder с явным параметром подсказок;
- собрать owner/member text, keyboard и command role через публичные сервисы;
- добавить bundle-level registrar для `wsp:home` раньше owner-controls;
- перевести help-toggle на тот же presentation contract;
- перевести тесты с private keyboard helper;
- сохранить callback data, тексты, роли и Telegram command scopes.

### Критерии готовности

- canonical `wsp:home` не импортирует `workspace_owner_controls`;
- help-toggle не вызывает `_workspace_home_keyboard`;
- owner и member используют одну view-модель;
- role-aware modules и button hints загружаются через публичные service methods;
- bundle-level home handler зарегистрирован раньше child routers;
- functional и architecture regressions используют публичный contract;
- navigation inventory актуален и не содержит violations.

### Риски и ограничения

Legacy `_workspace_home_keyboard`, `_render_home`, `_render_member_home` и `handle_workspace_owner_home` пока физически остаются в `workspace_owner_controls.py`. Новый bundle-level handler перехватывает canonical callback раньше child router, поэтому legacy path недостижим в текущей композиции. Физическое удаление остаётся отдельным механическим срезом для большого исторического файла.

## После завершения

### Фактически сделано

- добавлен `workspace_home_presentation.py` с immutable `WorkspaceHomePresentation`;
- опубликован `build_workspace_owner_home_keyboard`;
- добавлен role-aware `build_workspace_home_presentation` для owner и member;
- настройки, модули и button hints загружаются через публичные `WorkspaceProductService` contracts;
- добавлен `workspace_home_controller.py` с bundle-level registrar;
- `archive_and_public.py` регистрирует canonical home до `workspace_owner_controls_router`;
- `workspace_home_hint_controller.py` переведён на общий presentation builder;
- тесты keyboard, owner/member presentation, hint boundary и router order переведены на публичный API;
- Telegram navigation inventory обновлён до 443 Python-файлов без violations.

### Миграции и совместимость

Миграции не требуются. `wsp:home`, `wsp:helptoggle`, onboarding callbacks, роли, module visibility, button labels, тексты home-панели и scoped Telegram commands сохранены.

### Проверки

- добавлены functional owner/member presentation tests;
- добавлены architecture regressions для отсутствия private owner-controls dependency;
- добавлен regression bundle-level registration order;
- полный type check, test suite, project notes contract и Docker build выполняются в PR CI.

### PR и commit

- ветка: `agent/workspace-home-presentation-contract`;
- PR создаётся после финального сравнения с `main`.

### Незавершённое

Функциональных незавершённых пунктов в рамках runtime-переключения нет. Legacy home и archive dashboard helpers остаются физически в `workspace_owner_controls.py`, но больше не являются canonical входами.

### Следующий шаг

Механически удалить из `workspace_owner_controls.py` недостижимые archive dashboard helpers и legacy home render path, затем вынести reference dashboard и workspace deletion в отдельные presentation/controllers slices.
