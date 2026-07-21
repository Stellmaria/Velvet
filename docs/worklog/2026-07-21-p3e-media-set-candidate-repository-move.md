# Сессия: P3E media set candidate repository move

- Дата: 2026-07-21
- ID: `2026-07-21-p3e-media-set-candidate-repository-move`
- Линия/фаза: P3E repository and root-module layout
- Статус: `завершено`
- Ветка: `agent/p3e-move-media-set-candidate-repository`
- Базовый commit: `2cff4b5d768a3d39b32f5c40bfd019fef906c489`

## Перед началом

### Цель

Перенести первый рабочий root repository `media_set_candidate_listing_repository` в канонический domain `velvet_bot.domains.media_sets`, перевести production/test consumers и удалить старый корневой implementation без изменения SQL или поведения выдачи кандидатов.

### Исходный контекст

После двух central facade retirements P3E baseline содержал 31 repository-модуль: 23 domain, 1 central и 7 root. `velvet_bot.media_set_candidate_listing_repository` имел одного production consumer (`media_set_candidate_listing.py`) и один test consumer (`test_media_set_candidate_policy.py`). Repository отвечает за пагинацию доступных media-set candidates и сортировку сначала по количеству доступных файлов, затем по score.

### Планируемый объём

- создать `velvet_bot/domains/media_sets/repository.py` с существующими моделями и repository implementation;
- создать публичный domain export;
- перевести production listing service на domain import;
- перевести repository policy test на domain import;
- удалить корневой repository implementation;
- обновить generated P3E inventory и regression contract;
- сохранить SQL и публичную listing function без изменений.

### Критерии готовности

- repository implementation находится в `domains/media_sets`;
- production и test consumers используют canonical domain path;
- старый root-файл отсутствует;
- repository count остаётся 31;
- domain count увеличивается 23 → 24;
- root count уменьшается 7 → 6;
- следующий root candidate определяется новым baseline;
- полный CI проходит.

### Риски и ограничения

Срез изменяет только физическое расположение и imports. Runtime installer `install_media_set_candidate_listing`, public function `list_media_set_candidates_by_size`, SQL, page-size policy, candidate ranking и filtering behavior не меняются. Миграции базы данных не требуются.

## После завершения

### Фактически сделано

- создан domain `velvet_bot.domains.media_sets`;
- repository implementation и `MediaSetCandidateIdPage` перенесены в `domains/media_sets/repository.py`;
- domain package экспортирует `MediaSetCandidateListingRepository` и page model;
- `velvet_bot/media_set_candidate_listing.py` использует canonical domain import;
- `tests/test_media_set_candidate_policy.py` проверяет canonical repository;
- корневой `velvet_bot/media_set_candidate_listing_repository.py` удалён;
- P3E regression contract проверяет отсутствие старого пути и наличие domain repository;
- generated baseline обновляется до 24 domain, 1 central и 6 root repositories;
- следующим кандидатом становится `velvet_bot.media_set_duplicate_actions_repository`.

### Миграции и совместимость

PostgreSQL migrations не требуются. Старый root import больше не поддерживается. Public listing API, installer side effect и database schema остаются прежними.

### Проверки

Сохраняются repository SQL-order assertions, service-order/filtering test и installer idempotency test. Дополнительно generated inventory проверяет физический перенос root → domain. Полный GitHub CI запускается в PR.

### PR и commit

PR создаётся из ветки `agent/p3e-move-media-set-candidate-repository`; итоговый squash commit фиксируется после зелёного CI.

### Незавершённое

В корне остаются 6 repository implementations. Domain `media_sets` пока содержит только candidate listing repository; соседние media-set repositories переносятся отдельными связанными срезами без смешивания поведения.

### Следующий шаг

Перенести `media_set_duplicate_actions_repository` в тот же domain `media_sets`, обновить его service/test consumers и удалить второй root implementation. После этого оценить объединение общих media-set repository contracts без слияния независимых SQL operations в один монолитный класс.
