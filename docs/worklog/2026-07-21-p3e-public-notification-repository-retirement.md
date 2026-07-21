# Сессия: P3E public notification repository retirement

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-public-notification-repository-retirement`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-retire-public-notification-repository`
- Базовый commit: `21dc016a7c5b783cecf8a892dce5ec8dd5b45a6d`

## Перед началом

### Цель

Удалить первый измеренный P3E export-only repository facade `velvet_bot.repositories.public_notification_repository`, не создавая нового compatibility path и не меняя рабочий public archive notification flow.

### Исходный контекст

P3E inventory зафиксировал 33 repository-модуля: 23 domain, 3 central и 7 root. `velvet_bot.repositories.public_notification_repository` имел 0 production consumers, 0 test consumers и единственную ссылку из `velvet_bot/repositories/__init__.py`. Поиск символа `PublicNotificationRepository` подтвердил отсутствие иных статических consumers. Сам модуль был compatibility facade над каноническим `PublicArchiveRepository`.

### Планируемый объём

- удалить export `PendingPublicNotification` и `PublicNotificationRepository` из `velvet_bot/repositories/__init__.py`;
- удалить мёртвый `public_notification_repository.py`;
- обновить generated repository layout inventory;
- закрепить отсутствие удалённого модуля regression-тестом;
- сохранить канонический public archive notification repository и runtime behavior без изменений.

### Критерии готовности

- удалённый module path отсутствует в коде и inventory;
- `velvet_bot/repositories/__init__.py` не экспортирует удалённые symbols;
- repository count уменьшается 33 → 32;
- central repository count уменьшается 3 → 2;
- domain/root counts остаются 23/7;
- следующий кандидат определяется новым baseline;
- полный CI проходит.

### Риски и ограничения

Срез удаляет исторический import path без facade, поскольку inventory и code search не нашли runtime или test consumers. SQL, миграции, public archive delivery, notification worker и Telegram contracts не меняются.

## После завершения

### Фактически сделано

- из `velvet_bot/repositories/__init__.py` удалены imports/exports `PendingPublicNotification` и `PublicNotificationRepository`;
- удалён `velvet_bot/repositories/public_notification_repository.py`;
- P3E regression contract требует отсутствие файла, module inventory entry и package symbols;
- repository baseline обновляется до 32 modules: 23 domain, 2 central и 7 root;
- package exports уменьшаются 24 → 23;
- modules без runtime consumers уменьшаются 4 → 3;
- следующим low-coupling кандидатом становится `velvet_bot.repositories.publication_repository`.

### Миграции и совместимость

Миграции базы данных не требуются. Исторический import `velvet_bot.repositories.public_notification_repository` и package export `PublicNotificationRepository` больше не поддерживаются. Канонические `PendingPublicNotification` и `PublicArchiveRepository` в domain public archive остаются без изменений.

### Проверки

Обновлены generated repository inventory contract и отдельные assertions удаления файла/exports. Полный GitHub CI запускается в PR.

### PR и commit

PR создаётся из ветки `agent/p3e-retire-public-notification-repository`; итоговый squash commit фиксируется после зелёного CI.

### Незавершённое

Остаются 2 central repositories, 7 root repositories и один export-only domain module `velvet_bot.domains.media_rework.repository`. `publication_repository` имеет только test consumer и package export, поэтому требует отдельной проверки исторического contract перед удалением либо переносом теста на canonical publication repository.

### Следующий шаг

Проверить `velvet_bot.repositories.publication_repository`: сравнить facade с `velvet_bot.domains.publication.repository`, перевести `tests/test_phase6_publication_repository.py` на canonical module и удалить central facade, если внешний runtime contract действительно отсутствует.
