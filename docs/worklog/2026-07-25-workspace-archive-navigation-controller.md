# Сессия: workspace archive navigation controller

- Дата: 2026-07-25
- ID: `2026-07-25-workspace-archive-navigation-controller`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/workspace-archive-navigation-controller`
- Базовый commit: `b5b0c3f67e2dfffd1485f9b5dc1fa7832fbf2cd6`

## Перед началом

### Цель

Продолжить уменьшение runtime-ответственности `workspace_owner_controls.py`: вынести навигацию личного архива, построение карточки медиа и Telegram send/edit fallback в отдельные публичные presentation/controller contracts.

### Исходный контекст

После PR #324 настройки доступа и скачивания уже перехватывались отдельным `workspace_media_policy_controller.py`, а archive dashboard перестал импортировать callback-класс из legacy owner router. Действия `open`, `show`, `close`, `empty` и `help`, а также полная клавиатура карточки всё ещё исполнялись только широким `WorkspacePersonalArchiveCallback` handler внутри `workspace_owner_controls.py`.

### Планируемый объём

- создать публичный presentation слой карточки личного архива;
- перенести keyboard builder, caption, UI context и Telegram send/edit fallback;
- создать отдельный controller для `open`, `show`, `close`, `empty`, `help`;
- сохранить существующий `wpa` wire-format и viewer/owner поведение;
- зарегистрировать navigation handler раньше policy и legacy owner router;
- добавить functional и source-level architecture regressions;
- обновить Telegram navigation inventory.

### Критерии готовности

- карточка архива строится без импорта `workspace_owner_controls.py`;
- owner/viewer состав кнопок совпадает с прежним поведением;
- пагинация сохраняет циклические offsets и текущий `media_id`;
- карточки отправляются с `protect_content=True`;
- `edit_media` сохраняет fallback на новое сообщение и удаление старого;
- `close` не требует workspace/DB resolution;
- bundle-level registration расположена раньше legacy owner router;
- navigation inventory не содержит violations.

### Риски и ограничения

Legacy функции физически остаются в `workspace_owner_controls.py`, но после регистрации нового navigation handler не получают соответствующие callback actions в runtime. Мутации, удаление и доставка оригиналов пока остаются в legacy handler и будут вынесены отдельными срезами.

## После завершения

### Фактически сделано

- добавлен `workspace_archive_navigation.py` с immutable UI context, полной клавиатурой карточки, caption formatter и Telegram send/edit функциями;
- сохранены owner-only кнопки, viewer navigation, личные отметки, публичные лайки, подписка, watermark, rework, visibility, +18, blur, settings, topic, delete и close;
- добавлен `workspace_archive_navigation_controller.py` для `open`, `show`, `close`, `empty`, `help`;
- сохранены archive module checks, viewer role checks и global owner semantics;
- `close` обрабатывается до workspace resolution;
- archive registrar теперь устанавливает navigation handler до media policy handler и до `workspace_owner_controls_router`;
- добавлены functional и architecture regressions;
- Telegram navigation inventory обновлён до 450 Python-файлов и 863 inline-кнопок без violations.

### Миграции и совместимость

Миграции не требуются. Формат callback остаётся `wpa:<action>:<workspace_id>:<character_id>:<offset>:<media_id>`. Сохранены тексты alert, `protect_content`, циклическая пагинация, oversized-image warning и fallback при невозможности Telegram заменить медиа.

### Проверки

- проверяется owner/viewer состав клавиатуры и точные callback payloads;
- проверяется предупреждение для image document больше 20 МБ;
- проверяется защищённая отправка photo-карточки;
- проверяется ранний `close` без workspace resolution;
- project notes contract, type check, полный test suite и Docker build выполняются в PR CI.

### PR и commit

- ветка: `agent/workspace-archive-navigation-controller`;
- PR создаётся после финального сравнения с `main`.

### Незавершённое

Функциональных незавершённых пунктов в рамках navigation среза нет. Legacy navigation helpers остаются физически в `workspace_owner_controls.py`, но canonical bundle-level handler перехватывает их callback actions.

### Следующий шаг

Вынести owner media actions `download`, `like`, `sub`, `watermark`, `rework`, `public`, `adult`, `blur`, затем отдельно delete confirmation и delete mutation. После этого широкий personal archive handler можно удалить из `workspace_owner_controls.py` механически.
