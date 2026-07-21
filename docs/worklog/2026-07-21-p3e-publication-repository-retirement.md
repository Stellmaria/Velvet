# Сессия: P3E publication repository facade retirement

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-publication-repository-retirement`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-retire-publication-repository`
- Базовый commit: `007b5f44d1340c3666d4fd795e3b6f0c00f7dbfa`

## Перед началом

### Цель

Удалить central facade `velvet_bot.repositories.publication_repository`, перевести его единственный исторический integration test на канонический domain repository и сократить общий каталог repositories до одного реально используемого модуля.

### Исходный контекст

После первого P3E retirement baseline содержал 32 repository-модуля: 23 domain, 2 central и 7 root. `velvet_bot.repositories.publication_repository` состоял из одного re-export `PublicationRepository` из `velvet_bot.domains.publication.repository`. Inventory фиксировал 0 production consumers, один test consumer и один package export из `velvet_bot/repositories/__init__.py`.

### Планируемый объём

- перевести `tests/test_phase6_publication_repository.py` на canonical domain import;
- убрать `PublicationRepository` из central package exports;
- удалить facade-файл `velvet_bot/repositories/publication_repository.py`;
- обновить generated P3E inventory;
- закрепить отсутствие обоих retired central facades regression-тестом;
- не менять implementation канонического publication repository.

### Критерии готовности

- integration test использует `velvet_bot.domains.publication.repository`;
- facade module и package export отсутствуют;
- repository count уменьшается 32 → 31;
- central repository count уменьшается 2 → 1;
- domain/root counts остаются 23/7;
- следующим кандидатом становится первый root repository;
- полный CI проходит.

### Риски и ограничения

Срез удаляет только import compatibility. SQL, транзакционные гарантии publication repository, migrations, publication queue и Telegram delivery не изменяются. Исторический central import больше не поддерживается.

## После завершения

### Фактически сделано

- integration test Phase 6 переведён на `velvet_bot.domains.publication.repository.PublicationRepository`;
- из `velvet_bot/repositories/__init__.py` удалён export `PublicationRepository`;
- удалён однофайловый central facade `velvet_bot/repositories/publication_repository.py`;
- regression contract проверяет отсутствие notification/publication central facades и exports;
- generated baseline обновляется до 31 modules: 23 domain, 1 central и 7 root;
- следующим кандидатом становится `velvet_bot.media_set_candidate_listing_repository`.

### Миграции и совместимость

PostgreSQL migrations не требуются. Канонический publication domain repository и его API не менялись. Исторические imports из `velvet_bot.repositories.publication_repository` и `velvet_bot.repositories.PublicationRepository` больше не поддерживаются.

### Проверки

Сохраняются два PostgreSQL integration test сценария: атомарный claim/publish/event и error transition. Дополнительно обновлён P3E generated inventory contract. Полный GitHub CI запускается в PR.

### PR и commit

PR создаётся из ветки `agent/p3e-retire-publication-repository`; итоговый squash commit фиксируется после зелёного CI.

### Незавершённое

В `velvet_bot/repositories` остаётся только `system_repository`, у которого есть реальные production/test consumers. В корне остаются 7 repository-модулей, каждый имеет один production consumer и как минимум один test consumer.

### Следующий шаг

Перенести `media_set_candidate_listing_repository` и связанный service/controller boundary в отдельный domain `media_sets`, оставив старый root path временным facade только при необходимости внешней совместимости. Физический перенос и изменение поведения не смешивать.
