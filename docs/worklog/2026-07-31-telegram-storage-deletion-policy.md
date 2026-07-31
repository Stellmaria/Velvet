# 2026-07-31 — Policy удаления Telegram Storage

- Дата: `2026-07-31`
- ID: `telegram-storage-deletion-policy`
- Линия/фаза: `security hardening`
- Статус: `завершено`
- Ветка: `agent/issue-507-storage-deletion-policy`
- Базовый commit: `e73aed68f6123b09c38f4ddfe6b1b96314f9240c`

## Перед началом

### Цель

Исключить удаление произвольных файлов и каталогов через Telegram Storage после успешной или дублированной выгрузки.

### Исходный контекст

`remove_paths()` преобразовывал входные пути через `Path.resolve()` и затем без allowlist выполнял `unlink()` либо `shutil.rmtree()`. `StorageCandidate.delete_paths` не доказывал принадлежность пути конкретному configured root. Ошибки удаления молча игнорировались, а объект мог быть отмечен `local_deleted` после частичного удаления.

### Планируемый объём

- ввести typed `DeletionPolicy`, plan/result/issue models;
- разделить allowlist по storage kind;
- запретить filesystem root, home, checkout, data root, `.git`, `.env*` и PostgreSQL volumes;
- проверять symlink-компоненты без следования к внешнему target;
- разрешить recursive deletion только отдельной temporary policy;
- повторно валидировать inode/type/mode/size непосредственно перед удалением;
- добавить dry-run CLI, audit events, tests и recovery runbook;
- не выставлять `local_deleted` при refusal или filesystem error.

### Критерии готовности

- внешний абсолютный путь и `..` escape не удаляются;
- symlink target снаружи allowlist сохраняется;
- symlink parent и configured symlink root блокируют операцию;
- directory deletion требует explicit recursive policy;
- настройки с пустым или опасным root завершаются fail-fast;
- policy refusal не вызывает частичное удаление других путей batch;
- duplicate upload использует ту же policy;
- dry-run показывает план без удаления;
- CI и security tests проходят.

### Риски и ограничения

Проектные release-архивы, лежащие непосредственно в checkout, больше не удаляются автоматически. Для автоматической очистки их требуется размещать внутри `STORAGE_RELEASE_DIRS`. Это намеренное ужесточение: checkout не становится deletion root ради удобства одного legacy-пути.

## После завершения

### Фактически сделано

Добавлен модуль `telegram_storage/deletion.py` с typed policy, plan item, issue и result. Планирование использует lexical containment, `lstat()`, проверку каждого родительского компонента и блокировку protected paths. Symlink удаляется как ссылка, а symlink в родительском пути или цепочке configured root отклоняется. Перед фактическим удалением повторно сверяются root, kind, inode, mode и размер; recursive directory дополнительно проверяет identity перед входом и финальным `rmdir()`.

`TelegramStorageSettings` сохраняет lexical identity configured paths вместо преждевременного `resolve()`, поэтому symlink evidence не теряется до policy validation. Для watermarks, backups, diagnostics, exports, codex, releases и rework формируются отдельные политики. При включённом auto-delete настройки проверяются до запуска миграции. Uploader отмечает объект `local_deleted` только при полном успешном результате.

Batch с policy refusal теперь fail-closed: если хотя бы один путь выходит из allowlist либо нарушает protected/symlink contract, не удаляется ни один запланированный путь. Runtime filesystem failures по-прежнему возвращают явный partial result для recovery и audit.

Для временных multipart/backups/Krita cleanup оставлена отдельная recursive policy с узкими staging и bridge roots. Добавлен CLI `scripts/telegram_storage_deletion_preflight.py`, который выводит policy inventory и выполняет dry-run конкретных путей без печати секретов.

### Миграции и совместимость

SQL-миграций нет. Формат Telegram Storage objects и HTTP/Telegram UI не меняется. Старое распаковывание `deleted, freed = remove_paths(...)` сохраняется через совместимый typed result iterator.

Поведение project-root release archives меняется намеренно: upload выполняется, но локальный файл остаётся до перемещения producer в configured release root или ручного безопасного удаления.

### Проверки

Добавлены тесты для:

- допустимого файла внутри allowlist;
- внешнего абсолютного пути и `..` escape;
- fail-closed batch при одном отклонённом пути;
- symlink на внешний файл, symlink parent, configured symlink root и symlink ancestor;
- existing regular file как недопустимого allowlist root;
- explicit recursive mode;
- dry-run;
- protected root/home/checkout/data paths;
- `.env` и `.git`;
- foreign Windows drive path на POSIX;
- duplicate upload refusal;
- filesystem deletion error без `local_deleted`;
- fail-fast empty/dangerous roots;
- preflight inventory без утечки secret.

Первый CI run дополнительно выявил flaky test Server Supervisor: один `recv()` иногда получал только HTTP headers. Тест исправлен чтением ответа до EOF; production-код Supervisor не менялся.

Generated architecture baseline пересобран в полном GitHub Actions checkout. Итоговые метрики: 629 production modules, 134748 LOC, 546 зарегистрированных violations/exemptions. Временные generator workflows удалили себя из ветки после записи результатов.

### PR и commit

- Issue: `#507`
- PR: `#521`
- Ветка: `agent/issue-507-storage-deletion-policy`
- Основные commits: connector-backed commits ветки и итоговый squash commit после merge.

### Незавершённое

После merge на production нужно выполнить deletion preflight с `.env.server` до следующего storage migration и проверить dry-run фактических путей по runbook.

### Следующий шаг

Получить зелёный финальный tests/type-check/docker-build/project-notes matrix, слить PR и выполнить production preflight до следующей очистки Telegram Storage.
