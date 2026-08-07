# Сессия: Telegram Storage topic integrity

- Дата: `2026-08-07`
- ID: `telegram-storage-topic-integrity-20260807`
- Линия/фаза: `Telegram Storage / production integrity`
- Статус: `частично`
- Ветка: `fix/storage-topic-integrity`
- Базовый commit: `0273e46cded65b12575956b1a4dc3f5cd2856305`

## Перед началом

### Цель

Остановить повторную публикацию неизменных DB backup и Rework snapshot в Telegram Storage и восстановить canonical публикацию Arthur Librarian в `Hermes Reports`, не ослабляя manual-first режим и security boundaries.

### Исходный контекст

Read-only диагностика production показала:

- hourly Telegram Storage migration выполняется успешно и без failed items;
- одинаковый `rework:snapshot:<content_hash>` накопил до `178` Telegram Storage objects с `178` разными file SHA;
- одинаковые backup logical identities накопили до `89` encrypted Telegram Storage objects с разными ciphertext SHA;
- `STORAGE_DELETE_AFTER_UPLOAD=false`, поэтому исходные backup продолжали попадать в каждый scan;
- Watermark storage целостен: все `305` approved watermark имеют storage record, а producer намеренно выключен `KRITA_WATERMARK_ENABLED=false`;
- Diagnostics работает по configured active-file grace и в этот change не входит;
- legacy `/app/runtime/supervisor/codex_tasks.json` отсутствует, тогда как canonical coder ledger находится внутри Hermes `/opt/data/orchestration/tasks.json`.

Backup dedupe выполнялся только после повторной упаковки и AES-GCM encryption. Новый nonce менял ciphertext SHA, поэтому `(kind, logical_key, sha256)` каждый раз выглядел новым объектом.

Rework semantic key уже использовал hash содержимого очереди, но новый snapshot сначала получал свежий `generated_at`; file SHA менялся и existing-object lookup не срабатывал.

Arthur report publisher уже присутствует в dedicated runtime, но пустые `ARTHUR_REPORT_*` превращались в `None`, поэтому publisher корректно ничего не отправлял.

### Планируемый объём

- semantic backup lookup по stable logical identity до ZIP/encryption;
- semantic Rework lookup по content hash до создания JSON;
- сохранить existing delete-after-upload policy для уже сохранённых backup;
- canonical Arthur report destination использовать как fallback при пустых dedicated overrides;
- добавить regression tests.

### Критерии готовности

- повторный scan неизменного backup не создаёт новый ZIP/ciphertext/Telegram object;
- повторный scan неизменного Rework snapshot не создаёт новый JSON/Telegram object;
- explicit Arthur report destination сохраняет приоритет, а пустые overrides ведут в canonical Hermes Reports topic;
- SQL schema и существующие production objects не меняются;
- protected CI проходит на exact PR head.

### Риски и ограничения

Codex Storage migration не получает raw Hermes ledger mount. Основной Velvet bot не должен читать полный `/opt/data/orchestration/tasks.json`; восстановление `Codex Patches` требует отдельного redacted/export boundary.

Existing Telegram duplicate cleanup не выполняется этим PR: сначала producer должен перестать создавать новые дубли. Watermark, Diagnostics, Inbox, Exports и Releases этим изменением не меняются.

## После завершения

### Фактически сделано

- добавлен `integrity_service.py`, расширяющий migration service stable semantic dedupe для backups и rework;
- package entry point переключён на integrity service, сохраняя codec-independent backup repository;
- при найденном existing backup новый ciphertext не создаётся, а tracked `backup_run` связывается с existing object;
- неизменный Rework snapshot считается skipped до записи нового JSON;
- Arthur при пустых `ARTHUR_REPORT_CHAT_ID`/`ARTHUR_REPORT_THREAD_ID` использует canonical Storage chat и `Hermes Reports` thread, сохраняя явные overrides;
- добавлены focused regression tests.

### Миграции и совместимость

SQL migrations нет. Существующие Telegram messages и PostgreSQL duplicate rows не удаляются. Existing storage object identity и backup encryption format не меняются; меняется только момент duplicate detection.

### Проверки

Protected CI запускается на exact PR head. Production acceptance после deployment: два последовательных scans без новых source changes должны давать `backups stored=0` и `rework stored=0`, а новый Arthur analysis должен публиковать один report в canonical `Hermes Reports`.

### PR и commit

PR: `#692 Fix Telegram storage semantic dedupe and Arthur reports`.

Feature implementation commit: `69bc000400ab43bbdef156cb84e1e3f838057f9a`; ветка затем синхронизирована с актуальным `main` и дополнена этой worklog записью.

### Незавершённое

- дождаться terminal protected CI на текущем head и merge только exact green head;
- production deployment/acceptance выполняется отдельно;
- отдельным bounded change восстановить `Codex Patches` через redacted export из canonical Hermes coder ledger, не монтируя raw ledger в основной bot;
- очистку старых duplicate Telegram messages/DB rows проектировать только после подтверждения, что producer больше не создаёт новые дубли.

### Следующий шаг

Дождаться зелёного CI и merge #692. Затем реализовать отдельный redacted terminal-only Hermes coder export для Storage topic `/7`.
