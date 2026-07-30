# Сессия: кнопочный запуск Qwen-сравнения в личном пространстве

- Дата: 22 июля 2026 года
- ID: `2026-07-22-workspace-qwen-comparison-flow`
- Линия/фаза: Velvet AI / personal workspace comparison UX
- Статус: `частично`
- Ветка: текущая локальная ветка
- Базовый commit: `0c2ca41d47498c641d6422f89bd10175b1512c0b`

## Перед началом

### Цель

Убрать необходимость вручную вводить `/compare_ref` для уже workspace-aware Qwen-сравнения: после нажатия кнопки референса пользователь отправляет результат, а бот запускает ту же проверенную операцию в текущем личном пространстве.

### Исходный контекст

`workspace_reference_library` уже хранит references и comparison reports с workspace boundary и строит кнопку «Сравнить результат», но она показывает инструкцию с slash-командой. Полный Quality Center, media sets и AI job registry не имеют общего tenant boundary и не включаются в этот срез.

### Планируемый объём

- добавить короткую FSM-сессию кнопочного сравнения, закрепляющую workspace, персонажа и выбранный референс;
- повторно проверять reviewer role, references/Qwen modules и workspace Qwen setting перед запуском;
- переиспользовать существующий локальный Qwen client и сохранение comparison report;
- сохранить `/compare_ref` как совместимый резервный вход;
- добавить тесты state/route contracts без добавления SQL в Telegram controller.

### Критерии готовности

- callback не может подменить foreign reference;
- результат, отправленный после кнопки, сравнивается только с закреплённым reference текущего workspace;
- выключенный Qwen или недостаточная роль прерывают сессию;
- системный workspace сохраняет прежний интерфейс;
- проверка не открывает общий Quality Center или чужие AI jobs.

### Риски и ограничения

FSM привязан к пользователю и чату, но живой Telegram и PostgreSQL run всё ещё нужны отдельно. Срез улучшает существующую comparison-функцию, не добавляет новую AI-предметную область и не переносит системную очередь.

## После завершения

### Фактически сделано

- кнопка `🤖 Qwen` в личном пространстве открывает только tenant-safe сценарий сравнения с личными референсами, без раскрытия Quality Center Velvet Anatomy;
- карточка личного референса переводит пользователя в FSM-сессию и просит отправить результат фотографией или изображением-документом;
- сессия сохраняет workspace, персонажа, reference ID, offset и total; перед сравнением reference повторно читается в сохранённом workspace и его ID сверяется;
- callback и result message проверяют reviewer role, references/Qwen module policy и настройку Qwen; при потере доступа сессия очищается;
- существующая `/compare_ref` сохранена и вызывает тот же helper, что и новый кнопочный сценарий;
- общий Qwen Quality Center, media sets, media AI profiles и AI-job registry не открываются пользователю, потому что пока не имеют полной tenant-aware границы;
- добавлены contract tests и обновлён generated Telegram navigation inventory.

### Изменённые модули и контракты

- `workspace_reference_library` получил `WorkspaceReferenceComparisonForm`, guarded Qwen entry и единый comparison helper;
- `tests/test_workspace_qwen_comparison_flow.py` фиксирует pinning workspace/reference и использование общего helper;
- navigation inventory отражает две новые inline-кнопки Qwen entry.

### Миграции и совместимость

Миграции не требуются: `reference_comparison_reports` уже содержит workspace-scoped composite constraints. Старый reply-command остаётся рабочим резервным путём.

### Проверки

- `.venv\\Scripts\\python.exe -m compileall -q velvet_bot tests` — success;
- `.venv\\Scripts\\python.exe -m unittest tests.test_workspace_qwen_comparison_flow tests.test_workspace_reference_library tests.test_workspace_guided_navigation tests.test_telegram_navigation_inventory -q` — 15 tests success, 3 PostgreSQL tests skipped without `TEST_DATABASE_URL`;
- `.venv\\Scripts\\python.exe scripts/telegram_navigation_inventory.py --root velvet_bot --check` — 657 inline buttons, 0 violations;
- `git diff --check` не полностью зелёный только из-за заранее существующих conflict markers в пользовательском `README.md`.

### PR и commit

Не созданы.

### Незавершённое

- живая Telegram-проверка: открыть Qwen → reference → «Сравнить результат» → отправить изображение;
- PostgreSQL integration run с `TEST_DATABASE_URL`;
- полноценные tenant-aware media AI profiles, media sets и AI-job history требуют отдельной migration/repository линии;
- tenant-aware Telegram export import не входит в Qwen scope.

### Следующий шаг

Спроектировать отдельную workspace-scoped таблицу/репозиторий AI job history и только затем переносить личные media quality и media-set операции из системного Quality Center.
