# 2026-07-30 — shared Telegram helpers

- Дата: 2026-07-30
- ID: `telegram-shared-helpers`
- Issue: #419
- Линия/фаза: P3 architecture / duplicate helper cleanup
- Статус: `foundation завершён, family migrations продолжаются`
- Ветка: `agent/shared-telegram-helpers`
- PR: #462

## Цель среза

Сделать duplicate/shared-helper debt воспроизводимым по всему production package,
ввести публичные presentation/application contracts и остановить новые блокирующие
private helper contracts между controllers, installers и media workers.

## Фактически сделано

- создан пакет `velvet_bot.presentation.telegram.shared`;
- добавлены typed contracts для safe edit, deletion, navigation, text chunking,
  Telegram media download и retry/backoff;
- safe edit подавляет только `message is not modified`;
- deletion подавляет только already-absent/not-found, остальные Telegram errors
  продолжают подниматься;
- shared editing/media не используют `except Exception`, `BaseException` или
  injectable broad exception classes;
- package-wide AST scanner покрывает routers, app/installers, workers, direct imports,
  module attributes, nested attributes, assignments и `importlib` access;
- exact fingerprints дополнены normalized и semantic near-duplicate detection;
- image/video original + preview delivery отражается как semantic family;
- для 14 helper families зафиксированы current owner, target contract, status и
  retirement issue;
- обязательные private contracts `_task_line`, `_load_user_tasks`,
  `_task_list_keyboard`, `_MODEL_NAMES`, `_edit_or_answer`, `_validated_model` и
  `_reference_from_data` переведены на публичные API;
- SQL истории workspace tasks вынесен в application boundary;
- task payload/result mapping, model catalog и state compatibility получили
  отдельные публичные contracts;
- стандартные safe-edit фасады и два Telegram download/retry path мигрированы без
  изменения callback payloads, permissions, charging, provider routing или UX;
- добавлены regression tests на реальные known violations из app/installer graph;
- generated architecture, P2 stability и Telegram navigation inventories обновлены;
- delivery-card UX Ауф из актуального `main` сохранён при синхронизации ветки.

## Inventory результата

- production Python files: **594**;
- functions inventoried: **3304**;
- exact duplicate groups: **56**;
- normalized near-duplicate groups: **92**;
- semantic near-duplicate groups: **9**;
- blocking known private contracts: **0**;
- shared package boundary violations: **0**;
- registered transitional private accesses: **152**.

152 transitional accesses не объявлены завершёнными или canonical. Они являются
явным baseline для небольших family migrations и structural issues #455, #457,
#458, #460 и #463. PR #462 закрывает foundation и blocking contracts, но не
подменяет дальнейший cleanup красивым нулём в отчёте.

## Совместимость

Миграций базы данных нет. Callback payloads, пользовательские тексты, права доступа,
charging, provider routing и worker lifecycle не менялись. Локальные compatibility
aliases сохранены только там, где существующие consumers ещё зависят от имени;
scanner продолжает учитывать такие точки как transitional debt.

## Проверки итогового head

Head `fd1fb162d21a767b12a017ad3bdfe79cddcda3be`:

- full unit tests: **1756 tests**, успешно;
- type check: успешно;
- Docker build: успешно;
- project notes contract: успешно;
- `python scripts/inventory_telegram_helpers.py --check`: выполняется внутри
  regression test и успешно;
- unresolved review threads: 0;
- временный self-mutating workflow с `contents: write` удалён из PR.

## Следующий этап issue #419

- сливать family migrations небольшими reviewable PR;
- сначала убрать private safe-edit/navigation/state access из active installers;
- затем объединить progress and delivery primitives совместно с #455/#457;
- application task history/ownership завершать в #458;
- package-wide enforcement передать постоянным gates #460;
- закрыть #419 только после удаления зарегистрированного долга, который относится
  именно к shared-helper contracts, и обновления umbrella #213.
