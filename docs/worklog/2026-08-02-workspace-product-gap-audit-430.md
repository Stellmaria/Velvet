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
- tests, type check, security supply chain и project notes зелёные.

### Риски и ограничения

Документальный аудит не заменяет живой Telegram smoke и не закрывает broad программы #410/#417/#426. Он также не должен расширяться в реализацию provider routes, notifications или production rollout. Статус `verified` означает наличие кода и regression contract, а не успешную эксплуатационную проверку конкретного deploy.

## После завершения

### Фактически сделано

- добавлен `docs/audits/workspace_product_gap_audit.json` с 16 каноническими строками и отдельной operational acceptance строкой;
- добавлен `scripts/audit_workspace_product.py`, который проверяет coverage, статусы, follow-up IDs, существование evidence/test paths и актуальность generated Markdown;
- добавлен `docs/audits/workspace_product_gap_audit.md` с таблицей requirement → implementation → tests → status → follow-up;
- добавлен regression suite `tests/test_workspace_product_gap_audit.py`;
- синхронизированы разделы 14–15 `docs/requirements/workspace_product.md` и workspace-раздел `README.md`;
- stale regression, требовавший называть завершённые inline pickers следующим этапом, заменён контрактом фактического завершения и ссылки на audit evidence;
- подтверждено, что character taxonomy, references, publications, analytics и team roles уже workspace-scoped;
- создан #561 для live owner/onboarding/destinations smoke;
- создан #562 для live role matrix и tenant isolation;
- создан #563 как ограниченный provider-neutral personal quality slice #417;
- existing #426 сохранена как отдельный video/animation subscriber notification extension без дубля;
- временные write-workflows и patch helper удалены, `project-notes-contract` возвращён к исходному read-only режиму.

### Миграции и совместимость

Миграции БД и runtime behavior не меняются. Audit manifest ссылается только на существующие public contracts, migrations, presentation routes и tests. Изменения канонического ТЗ уточняют фактический статус и не объявляют live acceptance завершённой.

### Проверки

Выполнены focused contracts:

```bash
python scripts/audit_workspace_product.py --check
python -m unittest tests.test_workspace_product_gap_audit -v
python scripts/ci_preflight.py
```

На PR #564 проходят полный test matrix, type check, security supply chain и project notes contract. Documentation-only изменение не создаёт отдельный Docker build по текущим path filters.

### PR и commit

- PR: #564 `Audit canonical workspace product contract`;
- ветка: `audit/workspace-spec-430`;
- squash merge выполняется с exact-head guard после зелёного финального CI;
- итоговый merge commit фиксируется GitHub в PR и issue #430.

### Незавершённое

В рамках #430 незавершённых code-задач нет. Реальные остатки вынесены в #561, #562, #563 и существующую #426; live acceptance намеренно не подменяется зелёным CI.

### Следующий шаг

После merge #564 взять bounded code issue #563 и довести его отдельным PR, не смешивая с live-smoke #561/#562.
