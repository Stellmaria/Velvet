# Worklog: независимый lifecycle ключей backup

Дата: 2026-08-02  
Issue: #508  
PR: #560

## Цель

Отделить долговременное шифрование backup от оперативных authentication tokens, добавить versioned key ID, historical keyring, совместимый restore старых объектов и проверяемую процедуру rotation/re-encryption.

## Реализовано

### Формат и keyring

- Добавлен формат `VELVET-AESGCM2`.
- Key ID хранится в authenticated header и не может быть незаметно изменён без отказа GCM verification.
- Active key задаётся через `STORAGE_ENCRYPTION_ACTIVE_KEY_ID` и `STORAGE_ENCRYPTION_SECRET`.
- Historical decrypt-only keys задаются JSON-объектом `STORAGE_ENCRYPTION_KEYRING`.
- Legacy `VELVET-AESGCM1` поддерживается только через явно выбранный `STORAGE_ENCRYPTION_LEGACY_KEY_ID`.
- `BOT_TOKEN` и `SUPERVISOR_TOKEN` удалены из encryption fallback path.
- Keyring `repr` и owner-visible status содержат только IDs, без secrets или derived material.

### Atomic restore и re-encryption

- Encrypt/decrypt пишут во временный файл в destination directory и выполняют atomic `os.replace` только после успешной финализации.
- Повреждённый header, неизвестный key ID, неправильный key или повреждённый tag не создают частичный restore.
- Существующий destination не удаляется при неуспешной расшифровке.
- `reencrypt_file` расшифровывает старый объект, шифрует под active key, повторно расшифровывает candidate и сверяет plaintext SHA-256 до возврата результата.
- Исходный encrypted object остаётся неизменным; удаление возможно только отдельным подтверждённым шагом после restore verification.

### Storage metadata и operator visibility

- Новый backup manifest содержит `encryption_key_id` и `AES-256-GCM+scrypt:v2`.
- Database storage object получает ту же encryption version и key ID в manifest metadata.
- `/storage_keys` показывает active/available IDs, количество legacy объектов и номера backup без доступного decrypt key.
- Команда и diagnostics не выводят key material.
- Добавлен CLI `scripts/storage_backup_keys.py` с командами `inspect`, `check`, `decrypt`, `reencrypt`.

### Production validation

- Server preflight требует отдельный `STORAGE_ENCRYPTION_ACTIVE_KEY_ID` и dedicated secret.
- Проверяются key ID format, JSON historical keyring, минимальная длина каждого key и наличие legacy ID в keyring.
- Preflight блокирует совпадение любого backup key с `BOT_TOKEN` или `SUPERVISOR_TOKEN`.
- `.env.example` и `.env.server.example` дополнены lifecycle-переменными без реального key material.

### Runbook

`docs/BACKUP_KEY_LIFECYCLE.md` документирует:

- independent auth/backup rotation;
- escrow и offsite copy;
- последствия потери key;
- owner/local availability checks;
- migration `VELVET-AESGCM1`;
- disposable DB restore verification;
- verified re-encryption;
- порядок удаления старого object и retirement historical key.

## Regression tests

Покрыты:

- отсутствие auth-token fallback;
- независимость restore от ротации `BOT_TOKEN` и `SUPERVISOR_TOKEN`;
- authenticated key ID без утечки secret;
- historical key restore;
- terminal unknown key ID;
- legacy v1 restore через explicit legacy ID;
- сохранение существующего destination при corrupted tag;
- отсутствие partial files;
- verified re-encryption;
- preflight missing key ID и auth-secret reuse;
- сохранение старого Telegram Storage contract.

## Проверки

Focused integration workflow прошёл:

```bash
python -m compileall -q scripts velvet_bot tests
python -m unittest \
  tests/test_storage_encryption_keyring.py \
  tests/test_telegram_storage_center.py \
  tests/test_server_preflight.py -v
```

Одноразовый write-workflow удалён до финального CI. Полный tests/type/security/Docker результат фиксируется в PR #560 перед merge.

## Production migration после merge

Merge не удаляет legacy keys и не запускает массовую re-encryption автоматически. На VPS требуется отдельное контролируемое окно:

1. инвентаризировать существующие encrypted backup;
2. определить legacy key поколения;
3. добавить historical/legacy IDs без вывода secrets;
4. выполнить `/storage_keys`;
5. восстановить каждое поколение в disposable PostgreSQL;
6. перешифровать критичные объекты под active key;
7. удалить legacy object и key только после verified replacement и завершения retention.
