# Независимый lifecycle ключей backup

- Дата: 2026-08-02
- ID: VELVET-508
- Линия/фаза: Линия A / Backup cryptography и recovery
- Статус: `частично`
- Ветка: `security/backup-keyring-508`
- Базовый commit: `aa7684229c419da1c781e4bfaa2e9808372e32a2`

## Перед началом

### Цель

Закрыть issue #508: отделить долговременное шифрование backup от `BOT_TOKEN` и `SUPERVISOR_TOKEN`, добавить versioned key ID, active/historical keyring, совместимый legacy restore и проверяемую rotation/re-encryption процедуру.

### Исходный контекст

На базовом commit Telegram Storage использовал формат `VELVET-AESGCM1` без key ID. Если `STORAGE_ENCRYPTION_SECRET` отсутствовал, settings переходили к `SUPERVISOR_TOKEN`, затем к `BOT_TOKEN`. Ротация authentication token могла сделать старые backup недоступными, а metadata не позволяла определить нужное поколение ключа.

### Планируемый объём

- удалить authentication-token fallback;
- добавить authenticated v2 header с key ID;
- добавить active и historical keyring;
- сохранить explicit legacy v1 restore;
- сделать decrypt/re-encryption атомарными и проверяемыми;
- добавить preflight и owner-visible availability check без утечки secrets;
- добавить CLI, regression tests и lifecycle runbook;
- пройти полный CI и слить PR.

### Критерии готовности

- `BOT_TOKEN` и `SUPERVISOR_TOKEN` не участвуют в encryption key selection;
- новые backup содержат authenticated key ID и metadata version v2;
- historical и legacy keys расшифровывают старые поколения;
- неизвестный key ID завершается понятной terminal ошибкой без secret leakage;
- повреждённый header/tag не создаёт partial restore и не заменяет существующий destination;
- re-encryption повторно расшифровывает candidate и сверяет plaintext SHA-256;
- preflight отклоняет missing/invalid/reused keys;
- focused и full CI зелёные, PR слит, issue закрыта.

### Риски и ограничения

Потерянный AES-GCM key восстановить невозможно. Legacy v1 не содержит key ID, поэтому выбор старого ключа допускается только через явный `STORAGE_ENCRYPTION_LEGACY_KEY_ID` после инвентаризации и test restore. Merge не должен автоматически удалять старые объекты или historical keys.

## После завершения

### Фактически сделано

- добавлен `VELVET-AESGCM2` с authenticated key ID;
- добавлен `StorageEncryptionKeyring` с active, historical и legacy IDs;
- удалён fallback на auth tokens;
- storage settings, migration service и metadata переведены на keyring/version v2;
- encrypt/decrypt используют temporary destination и atomic replace;
- re-encryption проверяет новый объект повторным decrypt и SHA-256;
- добавлены `/storage_keys` и `scripts/storage_backup_keys.py` без вывода key material;
- server preflight проверяет key IDs, historical JSON, длину keys и auth-token reuse;
- env examples, focused tests и `docs/BACKUP_KEY_LIFECYCLE.md` обновлены;
- одноразовый write-workflow удалён до финального CI.

### Миграции и совместимость

Миграции схемы БД не требуются: key ID сохраняется в существующем JSON manifest. Новые объекты используют v2. Старые v1 продолжают читаться только при наличии explicit legacy key ID. Historical keys остаются decrypt-only до завершения retention и подтверждённого restore/re-encryption каждого поколения.

### Проверки

Пройдены focused contracts:

```bash
python -m compileall -q scripts velvet_bot tests
python -m unittest \
  tests/test_storage_encryption_keyring.py \
  tests/test_telegram_storage_center.py \
  tests/test_server_preflight.py -v
```

Type check зелёный. Финальные tests, security supply chain, Docker build и project notes повторно запускаются на чистом head без временного workflow.

### PR и commit

Draft PR: #560. Integration commit: `569d60eb2780d60baccbd1514d93f05faa651110`. Итоговый merge commit будет зафиксирован после зелёного CI.

### Незавершённое

Дождаться полного CI, устранить возможные static/security/test findings, обновить PR checklist, снять draft и выполнить squash merge с exact head SHA.

### Следующий шаг

Пройти финальные checks PR #560 и слить в `main`. Production key inventory, escrow, disposable restore и legacy re-encryption выполняются отдельным контролируемым rollout после merge по `docs/BACKUP_KEY_LIFECYCLE.md`.
