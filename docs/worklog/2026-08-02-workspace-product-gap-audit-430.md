# Gap-аудит канонического ТЗ workspace

- Дата: 2026-08-02
- ID: VELVET-430
- Линия/фаза: Линия Workspace / product contract audit
- Статус: `завершено`
- Ветка: `audit/workspace-spec-430`
- Базовый commit: `28297440ba53f337ba7361572129b3cd8ba47343`

## Перед началом

### Цель

Закрыть issue #430: сопоставить обязательные разделы `docs/requirements/workspace_product.md` с текущим кодом и regression tests, отделить реальные gaps от устаревших worklog-ограничений и оформить bounded follow-up без дублирования #410, #417 и #426.

### Исходный контекст

Каноническое ТЗ всё ещё называло workspace wiring character taxonomy, references, publications, analytics и team roles «следующим этапом». После этого текста в `main` были слиты отдельные срезы inline pickers, workspace reference library, publication queues, personal analytics, member dashboard, team roles, onboarding, destinations и media controls. Без повторного аудита документация продолжала изображать уже реализованное как backlog, потому что документы тоже умеют накапливать технический долг, только без stack trace.

### Планируемый объём

- покрыть матрицей все разделы 1–16 канонического ТЗ;
- для каждой строки указать implementation evidence, tests, status и follow-up;
- добавить воспроизводимый manifest и generator/check script;
- исправить устаревшие разделы ТЗ и README;
- создать небольшие child issues только для реальных code/live gaps;
- использовать существующую #426 вместо дублирования subscriber notification gap;
- пройти полный CI и слить PR.

### Критерии готовности

- каждый обязательный раздел 1–16 присутствует в machine-readable manifest;
- все evidence/test paths существуют;
- generated Markdown побитово соответствует manifest;
- старый roadmap не утверждает, что уже слитые workspace flows отсутствуют;
- live acceptance отделена от code completion;
- #561/#562 связаны с aggregate smoke #410;
- #563 является bounded code slice #417;
- #426 переиспользована как существующий extension issue;
- tests, type check, Docker, security и project notes зелёные.

### Риски и ограничения

Документальный аудит не заменяет живой Telegram smoke и не закрывает broad программы #410/#417/#426. Он также не должен расширяться в реализацию provider routes, notifications или production rollout. Статус `verified` означает наличие кода и regression contract, а не успешную эксплуатационную проверку конкретного deploy.

## После завершения

### Фактически сделано

- добавлен `docs/audits/workspace_product_gap_audit.json` с 16 каноническими строками и отдельной operational acceptance строкой;
- добавлен `scripts/audit_workspace_product.py`, который проверяет coverage, статусы, follow-up IDs, существование evidence/test paths и актуальность generated Markdown;
- добавлен `docs/audits/workspace_product_gap_audit.md` с таблицей requirement → implementation → tests → status → follow-up;
- добавлен regression suite `tests/test_workspace_product_gap_audit.py`;
- подтверждено, что character taxonomy, references, publications, analytics и team roles уже workspace-scoped;
- создан #561 для live owner/onboarding/destinations smoke;
- создан #562 для live role matrix и tenant isolation;
- создан #563 как ограниченный provider-neutral personal quality slice #417;
- existing #426 сохранена как отдельный video/animation subscriber notification extension без дубля.

### Миграции и совместимость

Миграции БД и runtime behavior не меняются. Audit manifest ссылается только на существующие public contracts, migrations, presentation routes и tests. Изменения канонического ТЗ уточняют фактический статус и не объявляют live acceptance завершённой.

### Проверки

Планируемый focused contract:

```bash
python scripts/audit_workspace_product.py --check
python -m unittest tests.test_workspace_product_gap_audit -v
python scripts/ci_preflight.py
```

После открытия PR выполняются полный test matrix, type check, Docker, security supply chain и project notes contract.

### PR и commit

PR будет открыт после синхронизации канонического ТЗ и README. Финальный merge commit фиксируется после зелёного CI.

### Незавершённое

В рамках #430 отсутствует code implementation follow-up: реальные остатки вынесены в #561, #562, #563 и существующую #426. До merge требуется обновить канонические документы, пройти CI и проверить exact head.

### Следующий шаг

Синхронизировать `docs/requirements/workspace_product.md` и `README.md` с audit matrix, открыть PR, устранить findings и выполнить squash merge с head guard.
