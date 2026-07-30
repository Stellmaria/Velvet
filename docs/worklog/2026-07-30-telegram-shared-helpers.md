# 2026-07-30 — shared Telegram helpers

- Дата: 2026-07-30
- ID: `telegram-shared-helpers`
- Issue: #419
- Линия/фаза: P3 architecture / duplicate helper cleanup
- Статус: `частично`
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

## После завершения

### Фактически сделано

- создан пакет `presentation.telegram.shared`;
- добавлены editing, navigation, deletion, media и text contracts;
- стандартные локальные safe-edit реализации переведены на shared editing contract;
- два Telegram download/retry path переведены на shared media contract;
- шесть private cross-controller helper imports заменены публичными контрактами;
- `safe_analytics_edit` переведён на shared editing contract;
- добавлены AST inventory, machine checks и regression tests;
- ветка синхронизирована с актуальным `main` без потери delivery-среза Ауф.

### Миграции и совместимость

Миграций базы данных нет. Callback payloads, пользовательские тексты, права доступа,
provider routing и worker lifecycle не изменены. Совместимые локальные aliases сохранены
там, где существующие consumers и regression tests зависят от старого имени.

### Проверки

- helper boundary CI: успешно, 588 production Python files, 55 duplicate groups,
  private helper imports: 0;
- type check: успешно;
- project notes contract: успешно;
- Docker build: успешно на предыдущем полном срезе, повторный прогон выполняется;
- полный tests workflow нашёл только compatibility alias `_download_file` и два
  устаревших generated P2 inventory; исправления подготовлены без возврата helper-долга.

### PR и commit

- PR: #462;
- текущая ветка: `agent/shared-telegram-helpers`;
- итоговый merge commit будет зафиксирован после полного завершения issue #419.

### Незавершённое

- восстановить compatibility alias `_download_file`;
- регенерировать P2 stability inventory после централизации broad exception dispatch;
- получить зелёный полный CI;
- обновить umbrella #213 и закрыть #419.

### Следующий шаг

Применить подготовленный compatibility repair, обновить generated contracts и выполнить
финальный полный CI на синхронизированной ветке.
