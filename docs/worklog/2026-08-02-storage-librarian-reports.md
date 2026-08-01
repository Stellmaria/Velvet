# Сессия: публикация отчётов Velvet Librarian

- Дата: 2026-08-02
- ID: `storage-librarian-reports-20260802`
- Линия/фаза: Hermes identities, Telegram Storage Librarian reports и installer hardening
- Статус: `частично`
- Ветка: `agent/storage-librarian-reports`
- Базовый commit: `0ad3e39e0607c55dc06fe4bdbb90ca3fdcaa779a`

## Перед началом

### Цель

Завершить оставшиеся хвосты Storage Librarian после успешного manual-first smoke-test:

- публиковать готовые анализы в Telegram topic `Hermes Reports`;
- перевести явную server-настройку анализатора с `hermes-librarian:v1` на `velvet-librarian:v2`;
- оставить массовую автоочередь выключенной;
- исправить ложное падение installer Каэля на root `docker compose exec`.

### Исходный контекст

На production успешно проанализирован Storage object `#2149`. Анализ сохранился в PostgreSQL и появился в `/storage_digest 1`, но отдельная тема `Hermes Reports` оставалась пустой. `/storage_librarian` показывал старую явную версию `hermes-librarian:v1`. Installer сущностей завершал фактическую установку, но падал на проверке UID, потому что обычный `docker compose exec` запускал shell от root вместо runtime-пользователя `hermes`.

### Планируемый объём

- отдельный Telegram publisher инфраструктурного слоя;
- подключение publisher к application service через protocol;
- явный флаг `STORAGE_LIBRARIAN_PUBLISH_REPORTS`;
- настройка v2 и публикации в installer;
- runtime UID-check через `s6-setuidgid`;
- тесты, runbook и architecture inventory.

### Критерии готовности

- завершённый анализ сохраняется независимо от результата публикации;
- при включённом флаге отчёт отправляется в `STORAGE_THREAD_ANALYSIS`;
- текст отчёта ограничен Telegram-лимитом и HTML-экранирован;
- отчёт содержит Storage ID и команду получения исходника;
- installer проверяет UID 10000 от имени `hermes`;
- CI полностью зелёный;
- production smoke подтверждает сообщение в теме `Hermes Reports`.

### Риски и ограничения

Публикация является вторичным каналом доставки: её ошибка не должна переводить успешно сохранённый анализ в failed. Повторный ручной анализ того же объекта намеренно создаст новый отчёт. Массовая очередь не включается этим срезом.

## После завершения

### Фактически сделано

- добавлен `TelegramStorageLibrarianReportPublisher`;
- application service получил optional publisher protocol;
- готовый анализ публикуется только после успешной записи в PostgreSQL;
- ошибка Telegram-публикации логируется и не отменяет анализ;
- installer выставляет `velvet-librarian:v2` и `STORAGE_LIBRARIAN_PUBLISH_REPORTS=true`;
- UID-проверка Каэля выполняется через `/command/s6-setuidgid hermes`;
- статус `/storage_librarian` показывает состояние публикации;
- добавлены contract и payload tests;
- runbook обновлён;
- package architecture inventory синхронизирован штатным генератором;
- Telegram navigation inventory синхронизирован штатным генератором;
- P2 stability inventory синхронизирован штатным генератором со schema version 77;
- оба временных write-workflow удалены из итоговой ветки.

### Миграции и совместимость

SQL-миграций нет. Существующие записи анализа сохраняются. Новый флаг по умолчанию выключен в коде и включается installer либо явной server-настройкой.

### Проверки

На исходном кодовом head подтверждены зелёные bounded mypy и project-notes. Первый чистый прогон выявил только generated drift: Telegram navigation учитывал 639 вместо 640 Python-файлов, а P2 inventory учитывал 103 вместо 104 одобренных broad boundaries. Оба реестра регенерированы штатными скриптами. Workflows на bot-generated commits получили GitHub `action_required` без jobs; этот обычный commit запускает финальный CI от владельца.

Ожидаются:

- полный tests workflow;
- architecture inventory preflight;
- повторный type-check;
- project notes contract;
- Docker Compose/build checks;
- production manual report smoke-test после merge.

### PR и commit

- PR: `https://github.com/Stellmaria/Velvet/pull/541`;
- generated inventory head: `54145a08a35fb230d952658b611f9bfa87583620`;
- проверенный финальный head: ожидается после финального CI;
- merge commit: ожидается после явного разрешения владельца.

### Незавершённое

- полный финальный CI на head без временных workflow;
- merge;
- production update и smoke-test темы `Hermes Reports`.

### Следующий шаг

Получить полностью зелёный CI. После отдельного разрешения владельца слить PR, обновить VPS, выполнить installers и повторно проанализировать небольшой диагностический объект `#2143`.
