# 2026-07-30 — shared Telegram helpers

- Дата: 2026-07-30
- ID: `telegram-shared-helpers`
- Issue: #419
- Линия/фаза: P3 architecture / duplicate helper cleanup
- Статус: `частично`
- Ветка: `agent/shared-telegram-helpers`
- Базовый commit: `5cc3676496a9a4d0e420e822ea6154ab639fcc9e`

## Перед началом

### Цель

Сделать duplicate/shared-helper debt воспроизводимым по всему production package,
ввести публичные presentation/application contracts и остановить новые блокирующие
private helper contracts между controllers, installers и media workers.

### Исходный контекст

В production-коде существовали многочисленные локальные safe edit, deletion,
navigation, chunking, retry, task mapping и delivery implementations. Первый вариант
inventory видел только часть `presentation.telegram.routers`, не покрывал динамические
module/private accesses из app/installers и не обнаруживал важные near-duplicates,
если names или строковые литералы различались.

### Планируемый объём

- расширить AST scanner на весь `velvet_bot`;
- учитывать direct imports, module/nested attributes, assignments и `importlib` access;
- добавить normalized и semantic near-duplicate detection;
- описать owner, target и retirement issue для всех helper families;
- ввести typed editing/deletion/navigation/text/media/retry contracts;
- мигрировать обязательные known private contracts;
- вынести task history SQL и mapping в application/domain boundaries;
- сохранить callback payloads, UX, permissions, charging и provider routing;
- добавить regression tests на реальные app/installer violations.

### Критерии готовности

- package-wide inventory воспроизводим;
- exact и важные near-duplicates видимы;
- blocking known private contracts равны нулю;
- shared presentation package не импортирует database/repository/domain services;
- shared editing/media не используют broad или injectable exception обходы;
- safe edit и deletion сохраняют точные Telegram error semantics;
- полный repository CI проходит;
- transitional debt остаётся явным baseline, а не объявляется завершённым.

### Риски и ограничения

Нельзя смешивать helper cleanup с изменением пользовательских меню, callback payloads,
permissions, charging, SQL semantics, provider routing или worker lifecycle. Temporary
hotfix/install roots нельзя объявлять canonical target contracts. Structural debt,
который относится к #455/#457/#458/#460/#463, должен оставаться зарегистрированным
до отдельных reviewable migrations.

## После завершения

### Фактически сделано

- создан пакет `velvet_bot.presentation.telegram.shared`;
- добавлены typed contracts для safe edit, deletion, navigation, text chunking,
  Telegram media download и retry/backoff;
- safe edit подавляет только `message is not modified`;
- deletion подавляет только already-absent/not-found;
- shared editing/media не содержат `except Exception`, `BaseException` или
  injectable broad exception classes;
- package-wide scanner покрывает 594 production Python files и 3304 functions;
- scanner учитывает routers, app/installers, workers, direct imports,
  module/nested attributes, assignments и `importlib` access;
- exact fingerprints дополнены 92 normalized и 9 semantic near-duplicate groups;
- image/video original + preview delivery отражается как semantic family;
- для 14 families зафиксированы current owner, target contract, status и
  retirement issue;
- обязательные `_task_line`, `_load_user_tasks`, `_task_list_keyboard`,
  `_MODEL_NAMES`, `_edit_or_answer`, `_validated_model` и `_reference_from_data`
  переведены на public API;
- workspace task history SQL вынесен в application boundary;
- task payload/result mapping, model catalog и state compatibility получили
  отдельные public contracts;
- standard safe-edit facades и два media download/retry path мигрированы;
- tests используют реальные known violations из app/installer graph;
- generated architecture, P2 stability и Telegram navigation inventories обновлены;
- delivery-card UX Ауф из актуального `main` сохранён;
- self-mutating feature workflow с `contents: write` удалён из PR.

### Миграции и совместимость

Миграций базы данных нет. Callback payloads, пользовательские тексты, права доступа,
charging, provider routing и worker lifecycle не изменены. Compatibility aliases
сохранены только для существующих consumers. Inventory фиксирует 152 transitional
private accesses как baseline для следующих family migrations и связанных issues,
не объявляя их canonical или завершёнными.

### Проверки

Для head `fd1fb162d21a767b12a017ad3bdfe79cddcda3be` успешно прошли:

- full unit tests: 1756 tests;
- type check;
- Docker build;
- project notes contract;
- `python scripts/inventory_telegram_helpers.py --check` через regression test;
- unresolved review threads: 0.

После обновления этого worklog повторный CI запускается на новом head.

### PR и commit

- PR: #462;
- ветка: `agent/shared-telegram-helpers`;
- foundation head до финального notes commit:
  `fd1fb162d21a767b12a017ad3bdfe79cddcda3be`;
- merge commit будет зафиксирован после зелёного CI итогового head.

### Незавершённое

- получить зелёный повторный project notes/tests на итоговом worklog commit;
- перевести PR #462 из draft и слить foundation-срез;
- продолжить #419 небольшими family migrations;
- убрать зарегистрированные shared-helper accesses, не относящиеся к отдельным
  structural issues;
- обновить umbrella #213 после завершённых slices;
- закрыть #419 только после выполнения всех критериев issue.

### Следующий шаг

После зелёного CI слить PR #462 как foundation, затем начать следующий reviewable
slice с private safe-edit/navigation/state accesses в active installers. Progress и
media delivery primitives развивать совместно с #455/#457, task history/ownership —
с #458, постоянные package gates — с #460.
