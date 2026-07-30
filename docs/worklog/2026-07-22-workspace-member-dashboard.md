# Сессия: вход участника в личное пространство

- Дата: 22 июля 2026 года
- ID: `2026-07-22-workspace-member-dashboard`
- Линия/фаза: Velvet Archive / стабилизация personal workspace UX
- Статус: `частично`
- Ветка: текущая локальная ветка
- Базовый commit: `0c2ca41d47498c641d6422f89bd10175b1512c0b`

## Перед началом

### Цель

Сделать существующие роли команды пригодными для ежедневной работы: участник чужого личного пространства должен открыть доступный ему архив из `/start`, увидеть свою роль и перейти только к уже разрешённым сценариям без ошибочного owner-only домашнего экрана.

### Исходный контекст

`workspace_members` и проверка ролей owner/admin/editor/reviewer/viewer уже существуют, но `/start` показывает «Моё пространство» только владельцу. Для участника этот путь либо отсутствует, либо приводит к owner-only callback. Модули самостоятельно повторно проверяют active workspace, роль и policy.

### Планируемый объём

- добавить отдельный список командных пространств в start state и кнопку входа;
- добавить member dashboard с выбором пространства, отображением роли и только существующими module routes;
- сохранить owner dashboard и его опасные настройки исключительно владельцу;
- повторно проверять membership и module policy на каждом переходе;
- добавить regression tests и обновить navigation inventory.

### Критерии готовности

- участник без собственных архивов видит понятный вход в командное пространство;
- выбор пространства делает его active workspace только после проверки membership;
- dashboard не открывает visibility, module toggle, onboarding или удаление;
- callbacks не становятся доверенным источником workspace/role;
- production Telegram router не получает SQL.

### Риски и ограничения

Это UX-слой над уже существующей моделью команды, а не расширение продукта в новую многопользовательскую предметную область. Часть модулей доступна не всем ролям: их кнопка объясняет требуемую роль, а конечный handler повторно применяет policy. Живой Telegram и PostgreSQL integration run потребуют отдельного окружения. Изменённый пользователем `README.md` не входит в срез.

### Обоснование стабилизации

Изменение улучшает уже работающие personal archive и workspace team roles: путь становится понятнее, а отказ owner-only экрана исчезает. Новая бизнес-область не вводится; используются существующие repository/service и callback contracts. Проверка — unit/source contracts, существующие workspace tests, compileall и navigation inventory. Границы сохраняются: handler вызывает domain service, SQL в Telegram router не добавляется, owner control routes не переиспользуются для member dashboard.

## После завершения

### Фактически сделано

- `/start` теперь отличает собственный архив от чужого личного пространства, куда пользователь добавлен в команду; для второго сценария показана отдельная кнопка «👥 Пространство команды»;
- добавлен выбор из доступных командных пространств, который сначала проверяет membership, а затем устанавливает только выбранное пространство active для этого пользователя;
- member dashboard показывает роль и только включённые разделы, совместимые с ней: viewer получает archive/references, reviewer — также Qwen/analytics, editor — characters/publications, admin — watermark/team;
- owner-only настройки (visibility, включение модулей, мастер, удаление) не выводятся на member dashboard;
- `WorkspaceProductService.list_modules_for_member` отдаёт module policy только после domain-проверки viewer membership; каждый конечный module handler сохраняет собственную проверку роли/module policy;
- добавлены regression tests для start entry, role matrix и повторной проверки membership.

### Изменённые модули и контракты

- `WorkspaceStartState` получил `member_workspaces`; это не меняет owner/public поля;
- `workspace_member_home` — новый Telegram router для `wsp:memberhome` и `wsp:memberselect`, зарегистрированный раньше generic workspace router;
- `workspace_ui` получил отдельные keyboards/formatters для командного сценария;
- access policy пропускает только два стартовых callback действия без active workspace, но handler заново проверяет доступ.

### Миграции и совместимость

Миграции не требуются: используется существующая таблица `workspace_members`. Старый owner dashboard и его callbacks не меняются; новый параметр `has_member_workspace` у `build_start_keyboard` имеет безопасное значение по умолчанию.

### Проверки

- `.venv\\Scripts\\python.exe -m compileall -q velvet_bot tests` — success;
- `.venv\\Scripts\\python.exe -m unittest tests.test_workspace_member_dashboard tests.test_workspace_product_access tests.test_workspace_guided_navigation tests.test_workspace_qwen_comparison_flow tests.test_workspace_onboarding tests.test_workspace_reference_library tests.test_workspace_publication_queues tests.test_workspace_analytics tests.test_workspace_team_watermark tests.test_telegram_navigation_inventory -q` — 75 tests success, 28 PostgreSQL tests skipped без `TEST_DATABASE_URL`;
- `.venv\\Scripts\\python.exe -m unittest discover -s tests -q` — success в текущей среде;
- `.venv\\Scripts\\python.exe scripts/telegram_navigation_inventory.py --root velvet_bot --check` — 420 Python files, 663 inline buttons, 0 violations;
- `.venv\\Scripts\\python.exe scripts/check_project_notes.py` — `Project notes contract: OK`;
- `git diff --check` не может стать полностью зелёным только из-за уже существующих conflict markers в пользовательском `README.md` (строки 1, 197, 249); новых whitespace errors среза не показано.

### PR и commit

Не созданы.

### Незавершённое

- живая Telegram-проверка: участник без собственного архива открывает `/start` → «Пространство команды» → выбирает архив, затем проверяются viewer/editor/admin наборы кнопок;
- PostgreSQL integration run с `TEST_DATABASE_URL`;
- full Quality Center, media AI profiles, media sets и AI job history по-прежнему системные: их перенос требует отдельной tenant-aware migration/repository линии, а не раскрытия чужих системных заданий.

### Следующий шаг

Подготовить отдельный workspace-scoped AI job repository/migration и только после этого переносить media-quality и media-set сценарии в личные пространства.
