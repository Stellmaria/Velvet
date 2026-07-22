# Workspace character presentation boundary

- Дата: 2026-07-22
- ID: workspace-character-boundary
- Линия/фаза: Workspace product / stabilization — character presentation boundary
- Статус: частично
- Ветка: `main` (создание рабочей ветки недоступно из sandbox)
- Базовый commit: `d146e08`

## Перед началом

### Цель

Убрать прямой PostgreSQL SQL и транзакции из legacy Telegram FSM управления персонажами personal workspace, направив его через существующий domain contract `velvet_bot.domains.workspaces.character_management`.

### Исходный контекст

Аудит обнаружил в `presentation/telegram/routers/workspace_admin.py` семь `database.acquire()` и операции изменения персонажа, category, universe и story links. Те же операции уже реализованы в domain module, но legacy text FSM дублирует их SQL.

### Планируемый объём

- заменить SQL helper-функции router на domain operations;
- сохранить callback/FSM и пользовательские тексты;
- добавить архитектурный regression test, запрещающий прямой database access в этом router;
- не менять схему, Telegram contracts и системный workspace.

### Критерии готовности

- `workspace_admin.py` не импортирует `Database` и не содержит SQL/database acquire;
- legacy text form сохраняет workspace tenant checks и прежние ошибки;
- regression tests подтверждают category/universe/story isolation;
- syntax и доступные unit tests проходят; ограничения окружения фиксируются.

### Риски и ограничения

- module-enabled check пока остаётся отдельным access query и будет вынесен последующим срезом вместе с общим workspace access contract;
- локальная `.venv314` не синхронизирована с `requirements.txt` (отсутствует Pillow), поэтому полный suite не выполняется до восстановления среды;
- новая миграция не нужна.

## После завершения

### Фактически сделано

- из `workspace_admin.py` удалены семь прямых подключений к PostgreSQL и все SQL-запросы legacy text FSM;
- добавлен `WorkspaceCharacterService`, инкапсулирующий существующие domain operations для create/list/load/category/universe/story;
- composition root передаёт сервис как `workspace_characters` в Telegram workflow data;
- module policy читается через `WorkspaceProductService.is_module_enabled()` после role check;
- taxonomy display использует domain product service и сохраняет фильтрацию только enabled элементов;
- PostgreSQL contract tests переключены с приватных router helpers на domain API;
- добавлен AST/text regression test, запрещающий `Database`, `database.acquire()` и SQL keywords в этом router.

### Изменённые модули и контракты

- `velvet_bot.presentation.telegram.routers.workspace_admin` зависит от `WorkspaceCharacterService` и `WorkspaceProductService`, а не от `Database`;
- `velvet_bot.app.dispatcher` публикует `workspace_characters` в workflow data;
- `WorkspaceProductService` получил query `is_module_enabled()`;
- добавлен export `WorkspaceCharacterService` из domain module.

### Миграции и совместимость

Миграции не добавлялись. Telegram commands, FSM name и callbacks сохранены. System workspace не затронут.

### Проверки

- `.venv\Scripts\python.exe -m compileall -q velvet_bot tests` — успешно;
- `.venv\Scripts\python.exe -m unittest discover -s tests -p test_workspace_character_taxonomy.py -v` — 3 passed, 3 PostgreSQL tests skipped без `TEST_DATABASE_URL`;
- `.venv\Scripts\python.exe -m unittest discover -s tests -p test_workspace_character_management.py -v` — 2 passed, 4 PostgreSQL tests skipped;
- `.venv\Scripts\python.exe -m unittest discover -s tests -p test_workspace_character_inline_pickers.py -v` — 3 passed, 3 PostgreSQL tests skipped;
- `.venv\Scripts\python.exe -m unittest discover -s tests -p test_p3_architecture_organization.py -v` — 5 passed;
- `git diff --check` — успешно.

### PR и commit

Локальный commit: `e1405d6 Refine workspace character boundary`. PR не создавался; commit находится на `main`, поскольку Supervisor выполняет update только этой ветки.

### Незавершённое

- PostgreSQL integration tests требуют отдельный `TEST_DATABASE_URL`;
- полный suite требует синхронизации локальной `.venv314` с `requirements.txt` (сейчас отсутствует Pillow);
- прямой persistence остаётся в восьми других presentation modules и выносится отдельными малыми срезами.

### Следующий шаг

Вынести read-only persistence из `workspace_character_pickers.py` в существующий domain character/taxonomy contract и добавить общий boundary test для всех Telegram routers.
