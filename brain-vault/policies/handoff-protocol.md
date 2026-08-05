---
id: handoff-protocol
type: policy
scope: shared
status: active
owner: kael
sensitivity: internal
version: 2
updated: 2026-08-04
---

# Протокол передачи задач

Каэль является control plane. Он классифицирует запрос, выбирает ровно один
project target и передаёт минимальный безопасный handoff по
`task-handoff.schema.json`. Кодеры являются execution plane и не управляют
другими сущностями.

## Состояния

Execution ledger: `proposed → accepted → running →
implemented_by_coder|blocked|failed|cancelled`.

Engineering readiness: `implemented_by_coder → review_pending →
review_changes_requested|review_approved → merge_authorized → merged →
rollout_pending → rollout_verified → completed`.

Только Каэль сопоставляет coder `run_id` с task ledger. Слово `completed` от
агента не является доказательством: ветка, PR, head SHA и CI проверяются через
фиксированный gateway. CI не является review approval. Merge и production update
требуют прав владельца; rollout-only проверки нельзя закрывать локальным отчётом.

## Минимальный handoff

- неизменяемые `task_id`, `source`, `project` и критерии готовности;
- очищенный контекст и ссылки на versioned project notes;
- разрешённые/запрещённые действия;
- ожидаемые тесты и формат результата;
- никаких токенов, `.env`, дампов, соседнего project context или длинных логов.
- effective workspace передаётся runner непосредственно перед execution и
  совпадает с `ledger.workspace_path`; статический legacy path запрещён.

Кодер возвращает structured result по `codex-task-output.schema.json`, включая
ветку, PR, тесты, blocker и необязательные memory candidates. Повтор после
ошибки создаёт новую попытку того же task, а не молча дублирует изменение.

Librarian никогда не получает handoff на изменение файлов. Он возвращает только
analysis/search result или memory proposal; Каэль решает, нужно ли передавать
proposal кодеру для versioned PR.
