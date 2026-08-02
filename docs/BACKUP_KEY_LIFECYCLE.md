# Lifecycle ключей шифрования backup

## Контракт

Backup encryption отделён от authentication domains. `BOT_TOKEN` и `SUPERVISOR_TOKEN` никогда не используются как fallback, не сравниваются с key material и могут ротироваться независимо.

Production задаёт:

```env
STORAGE_ENCRYPTION_ACTIVE_KEY_ID=backup-2026-08
STORAGE_ENCRYPTION_SECRET=<отдельный случайный secret минимум 32 символа>
STORAGE_ENCRYPTION_KEYRING={"backup-2026-05":"<historical secret>"}
STORAGE_ENCRYPTION_LEGACY_KEY_ID=legacy-bot-token-2026-07
```

`STORAGE_ENCRYPTION_KEYRING` содержит только read-only historical keys. Active secret задаётся отдельно. `STORAGE_ENCRYPTION_LEGACY_KEY_ID` нужен лишь для старого `VELVET-AESGCM1`, где key ID отсутствовал в header.

Новые backup используют `VELVET-AESGCM2`: key ID входит в authenticated header, а secret, derived key и salt-derived material никогда не попадают в metadata, Telegram caption, diagnostics или logs.

## Escrow и offsite

1. Создать active secret криптографическим генератором, не копировать bot/supervisor/API tokens.
2. Хранить production copy только в защищённом env/secret store с правами владельца.
3. Хранить минимум одну зашифрованную offsite escrow-копию вне VPS и вне Telegram Storage.
4. В escrow записывать key ID, дату активации, владельца и дату допустимого удаления, но не смешивать key material с backup-файлами.
5. После изменения escrow выполнить test restore в disposable PostgreSQL.

Потерянный AES-GCM key восстановить невозможно. Нет master bypass, recovery token или скрытого fallback. Если `/storage_keys` сообщает отсутствующий key ID, старый key нужно вернуть из escrow до любых операций удаления.

## Проверка доступности

В Telegram owner UI:

```text
/storage_keys
```

Команда показывает только active/available key IDs и номера объектов без доступного ключа. Secrets не выводятся.

Для локально скачанных объектов:

```bash
set -a
source /srv/velvet/.env.server
set +a
python scripts/storage_backup_keys.py inspect backup.velvet.enc
python scripts/storage_backup_keys.py check backup.velvet.enc
python scripts/storage_backup_keys.py decrypt backup.velvet.enc /tmp/backup.zip
```

`check` завершится кодом 2, если key ID неизвестен. Повреждённый header/tag не заменяет существующий destination и не оставляет partial restore.

## Ротация active key

1. Создать новый secret и новый неизменяемый key ID.
2. Переместить старый active secret в `STORAGE_ENCRYPTION_KEYRING` под прежним ID.
3. Установить новый `STORAGE_ENCRYPTION_ACTIVE_KEY_ID` и `STORAGE_ENCRYPTION_SECRET`.
4. Запустить server preflight. Он отклонит отсутствие key ID, короткие keys, invalid JSON и совпадение с `BOT_TOKEN`/`SUPERVISOR_TOKEN`.
5. Запустить `/storage_keys`; отсутствующих key IDs быть не должно.
6. Создать новый backup, скачать его и выполнить decrypt + restore в disposable DB.
7. Historical key остаётся в keyring до истечения retention всех связанных объектов и подтверждённого restore каждого поколения.

Ротация не требует немедленной перешифровки всего архива: v2 header сам выбирает historical key.

## Migration старых v1 backup

Старые `VELVET-AESGCM1` не содержат key ID. До отключения fallback:

1. Скачать inventory encrypted backup и определить поколения по object metadata и датам ротаций.
2. В изолированной среде проверить вероятные legacy secrets. Не печатать их и не передавать как CLI arguments.
3. Добавить подтверждённый secret в historical keyring под отдельным ID.
4. Установить этот ID как `STORAGE_ENCRYPTION_LEGACY_KEY_ID`.
5. Для каждого поколения выполнить decrypt и restore в disposable PostgreSQL, сверить manifest и `pg_restore` validation.
6. Критичные объекты перешифровать под active key:

```bash
python scripts/storage_backup_keys.py reencrypt \
  old.velvet.enc new.velvet.enc
python scripts/storage_backup_keys.py check new.velvet.enc
```

CLI всегда пишет отдельный destination, повторно расшифровывает candidate и сравнивает plaintext SHA-256. Исходный объект остаётся неизменным.

7. Загрузить новый encrypted object, проверить Telegram parts, metadata key ID и повторный restore.
8. Старый объект удалять только после verified replacement, завершения retention и отсутствия ссылок на старый key ID.

## Retirement historical key

Key можно удалить из keyring и escrow только когда одновременно выполнено:

- `/storage_keys` не показывает объектов с этим ID;
- retention старых объектов завершён;
- критичные backup перешифрованы и восстановлены в disposable DB;
- проверена offsite escrow нового active key;
- изменение прошло отдельный reviewable PR/change record.

Сначала удаляется старый encrypted object, затем после повторной проверки key availability удаляется historical key. Обратный порядок превращает backup в дорогой случайный шум, что обычно не является целью резервного копирования.
