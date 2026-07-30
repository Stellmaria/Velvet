# 2026-07-30 — миграция persistent identifiers Ауф

- Дата: 2026-07-30
- ID: `auf-persistent-identifiers`
- Линия/фаза: AI media generation / storage migration
- Статус: `завершено`
- Ветка: `agent/auf-persistent-identifiers`
- Базовый commit: `e24fae5f4a7b36ff2192be42807ccc227964156e`

## Перед началом

### Цель
Удалить последний deployed storage-слой Meow без потери кошельков, счетов, тарифов, task charges, runtime settings и workspace module preferences.

### Исходный контекст
Python runtime, Telegram protocol и пользовательский портал уже используют canonical Ауф API. Исторические таблицы, trigger names и module key оставались `meow_*` ради отдельной безопасной миграции.

### Планируемый объём
- добавить неизменяемую следующую миграцию `z024`;
- переименовать девять таблиц, sequences, constraints и indexes;
- пересоздать финансовые triggers/functions с именами Ауф;
- перенести module rows, user preferences и creation grants с `meow` на `auf`;
- переключить repositories и portal queries на новые identifiers;
- удалить legacy DI aliases, не затрагивая read-only Telegram callback compatibility.

### Критерии готовности
- старые migration-файлы z020-z023 не меняются;
- после initialize существуют только `auf_*` таблицы;
- существующие данные сохраняются через PostgreSQL RENAME, а не копирование;
- полный PostgreSQL test suite, type check, Docker build и restore drill проходят.

### Риски и ограничения
Старые callback prefixes и exact FSM class names остаются в `workspace_auf_legacy.py` до окончания переходного периода. Это transport compatibility, а не storage schema.

## После завершения

### Фактически сделано
- добавлена транзакционная migration `z024_auf_persistent_identifiers.sql`;
- runtime, wallet, pricing, invoices, reconciliation и portal queries используют `auf_*` tables;
- workspace module key, preferences и grants переведены на `auf`;
- settlement/requeue functions и triggers пересозданы под canonical именами;
- legacy DI aliases удалены из dispatcher;
- добавлены static и PostgreSQL integration contracts.

### Миграции и совместимость
Исторические z020-z023 сохранены без изменений. PostgreSQL `ALTER TABLE ... RENAME` сохраняет строки, FK-связи и object identity. Telegram legacy parsers не удаляются в этой фазе.

### Проверки
Полный CI и backup restore drill запускаются на PR #446.

### PR и commit
- PR: #446;
- storage migration head обновляется после исправлений CI;
- merge commit фиксируется после зелёного полного набора.

### Незавершённое
- удалить legacy callback/FSM parsers после достаточного переходного периода;
- удалить retired Python import shims после закрытия внешних веток.

### Следующий шаг
Выполнить restore drill и полный CI, затем слить migration PR до следующего функционального изменения Ауф.
