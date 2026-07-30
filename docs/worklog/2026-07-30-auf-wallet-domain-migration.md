# 2026-07-30 — перенос кошелька и списаний в домен Ауф

- Дата: 2026-07-30
- ID: `auf-wallet-domain-migration`
- Линия/фаза: AI media generation / wallet architecture cleanup
- Статус: `завершено`
- Ветка: `agent/final-auf-wallet-layer`
- Базовый commit: `922a92553123ca93ef85a1956af1952cee3cf74f`

## Перед началом

### Цель

Убрать оставшийся архитектурный слой Meow из кошелька Ауф: перенести реальные реализации ledger, pricing, invoices, reconciliation и task charging в `velvet_bot.domains.auf_wallet`, сохранив совместимость существующей базы и старых импортов.

### Исходный контекст

После интеграционного PR #403 пользовательский интерфейс назывался Ауф, однако `auf_wallet` только переэкспортировал реализации из `meow_wallet`. В старом пакете оставались модели, repository, service, pricing, purchase и charged queue. SQL-таблицы и callback payload уже используются production-данными и не могут быть одномоментно переименованы вместе с Python API.

### Планируемый объём

- перенести все wallet/economy реализации в canonical package `auf_wallet`;
- переключить production imports и тесты на `Auf*`;
- вынести Telegram wallet router в canonical path;
- превратить `meow_wallet` в короткие compatibility shims;
- не менять SQL-таблицы, idempotency keys и существующие callback payload;
- добавить контракт, запрещающий возврат реализации в retired package.

### Критерии готовности

- canonical package не импортирует `meow_wallet`;
- модели, repository, service, pricing, invoices и charged queue реально объявлены как `Auf*`;
- production dispatcher и installers используют canonical imports;
- старые Python imports продолжают работать через aliases;
- полный CI проходит.

### Риски и ограничения

Переименование SQL-таблиц `meow_*` требует отдельной транзакционной миграции production-данных и не входит в эту фазу. Callback-префиксы и workspace module key также сохраняются до отдельной dual-read/dual-write миграции. Механическое переименование Python API не должно затрагивать provider payload, ledger semantics или idempotency contract.

## После завершения

### Фактически сделано

- реальные модели перенесены в `auf_wallet/models.py`;
- ledger, reserve/capture/release/refund lifecycle перенесён в `auf_wallet/store.py`;
- экономика и пакетные цены перенесены в `auf_wallet/service.py`;
- versioned pricing перенесён в `auf_wallet/pricing.py`;
- invoices и reconciliation перенесены в `auf_wallet/purchase.py`;
- charged task queue перенесена в `auf_wallet/charged_queue.py`;
- Telegram router перенесён в `workspace_auf_wallet.py`;
- production imports и тесты переключены на canonical `Auf*`;
- `meow_wallet` сокращён до compatibility aliases;
- добавлен `test_auf_wallet_brand_boundary.py`, запрещающий canonical-коду зависеть от retired package;
- исправлены два ранее добавленных worklog-файла, нарушавших общий project-notes contract;
- callback командного пространства подтверждается до тяжёлых операций;
- architecture, P2 stability и Telegram navigation inventories пересобраны из актуального дерева;
- router bundle и button-audit contracts обновлены для нового командного экрана.

### Миграции и совместимость

SQL-схема не изменялась. Таблицы `meow_wallets`, `meow_wallet_entries`, `meow_generation_prices`, `meow_purchase_invoices`, `meow_task_charges` и связанные persistent identifiers сохраняются. Старые Python imports работают через aliases, поэтому внешние stacked-ветки не ломаются.

### Проверки

- bounded type check — успешно на первом head PR #405;
- Docker build и project notes contract — успешно на промежуточном head;
- generated architecture/P2/Telegram inventories синхронизированы после устранения шести устаревших contract assertions;
- полный CI повторно запускается на обычном commit после bot-generated inventory commit.

### PR и commit

- PR: #405;
- ветка: `agent/final-auf-wallet-layer`;
- первый functional head: `c8d49b4f164e15a32eb64248f29c009670ac88a7`;
- synchronized contracts head: `10d04accfa30dc0e5c4c777fd6a4e7bed86e9b38`;
- итоговый head и merge commit фиксируются после зелёного CI и слияния.

### Незавершённое

- отдельная SQL-миграция persistent `meow_*`-таблиц и module key;
- dual parsing и последующее удаление старых Telegram callback/FSM identifiers;
- переименование оставшихся generation-router файлов и callback classes после завершения протокольной миграции.

### Следующий шаг

Получить зелёный CI для PR #405, слить canonical wallet migration, затем отдельным PR внедрить новые `auf_*` callback/FSM identifiers с чтением старых payload до окончания переходного периода.
