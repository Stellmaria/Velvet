---
id: engineering-evidence
type: policy
scope: shared
status: active
owner: kael
sensitivity: internal
version: 1
updated: 2026-08-04
---

# Engineering readiness и доказательства

## Стадии

`implemented_by_coder → review_pending → review_changes_requested|review_approved
→ merge_authorized → merged → rollout_pending → rollout_verified → completed`.

Coder не проходит дальше `implemented_by_coder`. PR и CI необходимы, но не дают
review approval. Merge требует отдельного разрешения владельца, а локальные
проверки не закрывают rollout acceptance.

## Иерархия evidence

От сильного к слабому: host runtime acceptance; real container/integration;
integration test через публичный интерфейс; unit behavior; static contract;
source marker; agent report. Слабый уровень не подтверждает утверждение более
сильного уровня. Complex/high-risk protocol change требует integration evidence.

## Effective workspace и mutation

Источник истины о task checkout — `ledger.workspace_path`, который обязан
совпадать с process cwd. Shared/base, chat, legacy `/workspace` и соседние run
не являются task workspace. Расхождение завершается fail-closed.

`mutation_started` является OR доверенных сигналов: HEAD, branch/ref, index или
untracked changes, base checkout changes, execution event, push либо PR. Clean
working tree после commit не отменяет mutation. Agent report не может задавать
route или mutation evidence. Конфликт ledger и Git/GitHub блокирует pipeline.

## Review gate

High-risk review проверяет issue и changed-file coverage, обе стороны schemas,
secret/permission boundaries, lifecycle/idempotency, rollback safety, runtime
gaps и behavioral tests. Rollout-only checks остаются открытыми. Исправления
идут в существующем PR; после двух автоматических review-fix итераций с новым
blocking defect работа эскалируется владельцу либо независимому исполнителю.

## Checklist известных регрессий

- compose layers не дублируют `security_opt`, lifecycle использует один layer set;
- oneshot rerun доказывается фактическим lifecycle result;
- manifest-managed files не меняются после generation, verify идёт после
  последней atomic записи, group/world permission bits запрещены;
- direct/delegated schemas совместимы end-to-end;
- sandbox smoke реально запускает target command, host profile требует runtime probe;
- default branch и canonical service берутся из deployment contract;
- `mergeable=true` не является review approval, CI success недостаточен.
