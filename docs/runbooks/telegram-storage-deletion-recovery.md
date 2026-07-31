# Telegram Storage: безопасное удаление и recovery

## Назначение

Telegram Storage удаляет локальные файлы только после успешной загрузки и записи объекта в PostgreSQL. Удаление разрешено исключительно внутри корней, соответствующих типу объекта: backups, diagnostics, exports, releases, staging или Krita bridge.

`local_deleted` не выставляется, если хотя бы один путь был отклонён policy или не удалился из-за ошибки файловой системы.

## Preflight конфигурации

Запускайте из каталога приложения с production env:

```bash
python scripts/telegram_storage_deletion_preflight.py
```

Команда выводит только имена политик, разрешённые корни и флаг recursive. Значения секретов не печатаются.

Preflight завершится ошибкой до миграции, если:

- allowlist пуст при `STORAGE_DELETE_AFTER_UPLOAD=true`;
- корнем удаления назначены `/`, home, checkout приложения или `VELVET_DATA_DIR`;
- разрешённый корень совпадает с `.git` или PostgreSQL volume;
- корень является symlink.

## Dry-run конкретных путей

```bash
python scripts/telegram_storage_deletion_preflight.py \
  --kind exports \
  --path /app/runtime/exports/report.json
```

Для нескольких путей повторите `--path`. Dry-run ничего не удаляет и возвращает:

- `[PLAN]` для доказанно безопасных путей;
- `[REFUSE]` с typed code для отклонённых путей.

## Основные refusal codes

- `outside_allowlist`: путь не принадлежит корням выбранного типа;
- `allowlist_root`: попытка удалить сам разрешённый корень;
- `protected_path` / `protected_tree`: filesystem, home, checkout, data или database path;
- `blocked_name`: `.git` или `.env*`;
- `symlink_parent`: один из родительских компонентов является symlink;
- `recursive_not_allowed`: каталог передан политике, разрешающей только файлы;
- `changed_since_plan`: inode, mode, размер или тип изменился между plan и delete;
- `delete_failed`: файловая система отказала непосредственно при удалении.

Symlink, расположенный непосредственно внутри allowlist, удаляется как ссылка. Его внешний target не открывается и не удаляется. Symlink в родительском компоненте блокирует операцию целиком.

## Recovery после отказа

1. Не отключайте policy и не расширяйте allowlist до project/data root.
2. Найдите событие `telegram_storage_deletion_issue` в защищённом логе.
3. Запустите dry-run для того же `kind` и пути.
4. Исправьте конкретную причину:
   - неверный root в env;
   - файл создан вне предназначенного exports/releases/staging каталога;
   - parent symlink;
   - недостаточные owner/mode;
   - файл был заменён другим процессом после планирования.
5. Переместите артефакт в корректный configured root либо исправьте producer, затем повторите миграцию.
6. Убедитесь, что PostgreSQL object существует, а `local_deleted` остался false до полного удаления.
7. Ручное удаление через SSH выполняйте только после сравнения SHA256/metadata объекта и отдельного dry-run. Не меняйте код policy ради единичного файла.

## Recursive cleanup

Общие storage policies не удаляют каталоги рекурсивно. Recursive mode включён только для временного staging и Krita bridge cleanup, где каталог создаётся самим приложением и повторно проверяется перед каждым удалением компонента.

Project-root release archives после выгрузки сохраняются локально. Для автоматической очистки перенесите их в один из `STORAGE_RELEASE_DIRS`; добавлять весь checkout в allowlist запрещено.
