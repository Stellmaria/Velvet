# 2026-07-30 — shared Telegram helpers

- Дата: 2026-07-30
- Issue: #419
- Линия/фаза: P3 architecture / duplicate helper cleanup
- Статус: `в работе`
- Ветка: `agent/shared-telegram-helpers`
- Базовый commit: `39868c73e6a0b24f524d5801df715dde5dd87a7e`

## Перед началом

### Цель

Сделать duplicate/helper debt измеримым, ввести публичные Telegram presentation
contracts и остановить новые импорты приватных helper-функций между controllers.

### Исходный контекст

В production-коде существуют многочисленные локальные реализации safe edit, back
keyboards, deletion, chunking и progress updates. Часть повторов является реальным
дублированием, часть относится к compatibility/generated surface, а часть представляет
допустимые локальные шаблоны.

### Планируемый объём

- добавить AST inventory production Python;
- классифицировать exact function clones;
- ввести shared editing/navigation/deletion/text contracts;
- запретить helper-like private cross-controller imports;
- перевести первый совместимый safe-edit facade без изменения UX;
- получить список остаточного долга из CI и мигрировать семейства отдельными коммитами;
- обновить umbrella #213 после зелёного полного среза.

### Критерии готовности

- `inventory_telegram_helpers.py --check` проходит в CI;
- все девять семейств имеют публичный контракт;
- shared presentation package не импортирует domain/repository/database;
- private helper imports между router modules равны нулю;
- callback payloads и Telegram error behavior покрыты regression tests.

### Риски и ограничения

Нельзя смешивать cleanup с изменением пользовательских меню, permissions, SQL или
provider routing. `message is not modified` остаётся единственной молча игнорируемой
ошибкой safe edit; остальные ошибки должны продолжать подниматься.

## Текущее выполнение

- создан пакет `presentation.telegram.shared`;
- добавлены editing, navigation, deletion и text contracts;
- `safe_analytics_edit` переведён на shared editing contract;
- добавлены AST inventory, machine checks и regression tests;
- следующий шаг определяется точным CI inventory, а не ручным поиском по именам.
