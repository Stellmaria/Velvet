# Сессия: workspace archive actions and delivery controllers

- Дата: 2026-07-25
- ID: `2026-07-25-workspace-archive-actions-and-delivery`
- Линия/фаза: workspace architecture cleanup
- Статус: `завершено`
- Ветка: `agent/workspace-archive-mutations-and-cleanup`
- Базовый commit: `01e92a0f244fef0f315f3eb28b1d1986701a5eaf`

## Перед началом

### Цель

За один рабочий цикл вывести из `workspace_owner_controls.py` все оставшиеся живые действия callback-префикса `wpa`: социальные действия, изменения состояния медиа, watermark/rework, скачивание оригинала и удаление материала.

### Исходный контекст

Предыдущие срезы уже сделали каноническими workspace home, archive dashboard, reference dashboard, удаление workspace, media policy и навигацию карточки. Broad owner-router всё ещё исполнял `like`, `sub`, `watermark`, `rework`, `public`, `adult`, `blur`, `download`, `delete` и `deleteconfirm`, а access/page проверки повторялись между контроллерами.

### Планируемый объём

- добавить общий access/page boundary личного архива;
- вынести `like` и `sub` в отдельный social controller;
- вынести watermark, rework и visibility mutations;
- вынести отправку оригинала и двухэтапное удаление;
- зарегистрировать все действия раньше legacy owner-router;
- проверить полное и непересекающееся покрытие callback actions;
- обновить Telegram navigation inventory.

### Критерии готовности

- все известные `wpa` actions обрабатываются каноническими bundle-level handlers;
- action sets не пересекаются;
- viewer/owner, module и stale-media проверки сохранены;
- тексты, callback wire-format и поведение Telegram не меняются;
- legacy owner-handler не получает известные `wpa` actions в runtime;
- navigation inventory не содержит violations.

### Риски и ограничения

`workspace_owner_controls.py` пока физически содержит исторические реализации. Этот срез сначала прекращает их runtime-использование. Полное механическое удаление большого блока выполняется отдельно после зелёного CI, чтобы не смешивать перенос поведения и массовое удаление строк.

## После завершения

### Фактически сделано

- добавлен `workspace_archive_access.py` с единым разрешением workspace/role/module и загрузкой media page;
- navigation controller переведён на общий access boundary;
- добавлен `workspace_archive_social_controller.py` для личных/публичных лайков и подписки;
- добавлен `workspace_archive_mutation_controller.py` для watermark, rework, public, adult и blur;
- добавлен `workspace_archive_delivery_controller.py` для скачивания оригинала, confirmation UI и удаления;
- все новые handlers подключены через существующий archive registrar раньше broad owner-router;
- добавлена проверка полного непересекающегося покрытия известных `wpa` actions;
- добавлены функциональные проверки delete keyboard, access boundary и stale-media защиты;
- Telegram navigation inventory обновлён без violations.

### Миграции и совместимость

Миграции не требуются. Сохранён формат `wpa:<action>:<workspace_id>:<character_id>:<offset>:<media_id>`, старые Telegram-кнопки, owner-only ограничения, тексты уведомлений, storage semantics оригиналов, watermark prerequisites и порядок удаления архивных сообщений.

### Проверки

- action coverage и disjointness tests добавлены;
- delivery keyboard и shared access tests добавлены;
- architecture boundary tests добавлены;
- project notes contract, type check, полный test suite и Docker build выполняются в PR CI.

### PR и commit

- ветка: `agent/workspace-archive-mutations-and-cleanup`;
- PR создаётся после финального сравнения с `main`.

### Незавершённое

Исторический catch-all и его приватные helpers остаются физически в `workspace_owner_controls.py`, но после регистрации новых filters не получают ни одного известного `wpa` действия. Media policy controller пока содержит собственную копию access resolver и будет переведён на общий boundary при механической зачистке.

### Следующий шаг

После зелёного CI физически удалить из `workspace_owner_controls.py` недостижимые home/archive/reference/delete и personal archive blocks, убрать лишние imports и оставить только действительно принадлежащие router обязанности либо удалить router целиком.
