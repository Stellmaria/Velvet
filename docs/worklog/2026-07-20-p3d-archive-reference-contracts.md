# Сессия: P3D archive/reference contracts

- Дата: 2026-07-20
- ID: `2026-07-20-p3d-archive-reference-contracts`
- Линия/фаза: Velvet Archive, P3D
- Статус: `завершено`
- Ветка: `agent/p3d-archive-reference-contracts`
- Базовый commit: `acce484e22046c20bf46de32f95f435d9ebe64ed`

## Перед началом

### Цель

Убрать следующую связанную группу production-зависимостей от `velvet_bot.handlers.*`: parsing-функции архива и референсов, callback contracts и presentation helpers, которые уже имеют канонические реализации.

### Исходный контекст

После PR #221 legacy baseline составляет 19 consumer-файлов, 28 references и 17 legacy modules. Следующий безопасный срез включает archive/reference consumers и несколько прямых callback imports, которые можно перевести без изменения поведения.

### Планируемый объём

- вынести parsing-функции save/reference flows в публичные модули;
- перевести archive guest и reference controllers на публичные imports;
- убрать imports `handlers.admin_directory` из reference help;
- классифицировать и очистить связанные public archive/media presentation imports;
- обновить AST inventory и regression tests;
- удалить legacy alias только если его consumer count станет нулевым;
- не менять callback prefixes, команды, SQL и пользовательские тексты.

### Критерии готовности

- очищенные controllers не импортируют `velvet_bot.handlers`;
- parsing functions имеют один публичный источник истины;
- compatibility exports остаются только для внешних/тестовых consumers;
- legacy baseline уменьшается;
- полный test suite, Docker build и project notes contract проходят.

### Риски и ограничения

Импорт controller-to-controller заменяется публичным contract/helper module, а не новым универсальным `utils.py`. Handler alias удаляется только при нулевом production consumer count и наличии regression-проверки.


## После завершения

### Фактически сделано

- production imports `velvet_bot.handlers.*` сведены с 19 файлов / 28 references / 17 modules до **0 / 0 / 0**;
- парсинг `/save`, `/ref`, `/refs`, `/refadd` и выбора номера референса вынесен в публичные `archive/parsing.py` и `references/parsing.py`;
- canonical controllers сохраняют старые exported parser names для тестовой и внешней совместимости;
- owner menu, analytics, backup, publication, quality, Supervisor, archive и reference controllers переведены на canonical presentation imports;
- public archive sender получил публичное имя `send_public_archive_page` с временным compatibility alias старого `_send_public_archive_page`;
- удалён неиспользуемый `public_manager_preview_bridge.py`; public manager напрямую использует canonical preview override;
- architecture inventory обновлён: 68 handler aliases, 0 implementations, 114 root modules, 5 compatibility files и 8 активных runtime components;
- legacy consumer inventory и regression contract теперь запрещают любой новый production import `velvet_bot.handlers.*`.

### Миграции и совместимость

Миграции не требуются. Callback prefixes, callback payload fields, команды, SQL и пользовательские тексты не изменены. 68 handler aliases пока сохранены для compatibility-тестов и внешних import paths; этот срез закрывает production consumers, но не удаляет весь внешний compatibility API.

### Проверки

- целевой regression suite: 97 tests, success;
- `compileall`, legacy inventory `--check`, architecture inventory `--check` и `git diff --check`: success;
- полный локальный suite: 945 tests, success; 24 PostgreSQL integration tests skipped без `TEST_DATABASE_URL`;
- финальные GitHub Actions фиксируются на head PR #222.

### PR и commit

- PR: #222 `P3D: clean archive and reference contracts`;
- ветка: `agent/p3d-archive-reference-contracts`;
- production commit создаётся после полного локального прогона.

### Незавершённое

Production legacy consumers закрыты. Остаются 68 handler aliases, которые используют compatibility-тесты и потенциальные внешние imports, а также 8 runtime compatibility components и историческое размещение repositories/root modules.

### Следующий шаг

Мигрировать compatibility-тесты на canonical modules группами и удалять handler aliases только после нулевого test/external contract count. После этого перейти к P3E repository/root module layout и duplicate helper inventory.
