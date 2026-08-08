# VL quality owner-controlled queue

Date: 2026-08-08
Canonical issue: #630

## Goal

Replace immediate global quality enqueue/retry controls with a fail-closed owner plan/start flow. Production already has the worker gate and the 512-token quality budget; this slice prevents legacy or accidental archive backlog from becoming runnable merely because `AI_QUALITY_ENABLED` is later enabled.

## Changes

- add persistent `media_ai_quality_queue_plans` with owner, exact `media_ids`, requested limit, 15-minute expiry, start timestamp, and start count;
- add `media_ai_quality_checks.queue_plan_id` for queue provenance;
- quarantine pre-plan `pending`, `processing`, and `error` global quality rows to `skipped` during migration;
- replace immediate `enqueue_recent()` with `plan_recent()` followed by explicit `start_plan()`;
- replace global quality+semantic `retry_errors()` with a quality-only error plan;
- keep existing Telegram callback action names for compatibility, but make them render a confirmation plan instead of mutating the queue;
- expose controlled plan sizes 10, 25, and 100 for recent media, plus an error/quarantine plan;
- `start_plan()` can enqueue only the exact persisted ids, only for the owner who created the plan, once, before expiry;
- planning alone never inserts or updates `media_ai_quality_checks`;
- semantic `media_ai_profiles` are no longer touched by the global quality retry control.

## Legacy backlog policy

Before this migration there was no explicit owner plan/start boundary, so active global quality rows cannot prove authorization. The migration therefore converts legacy `pending`, `processing`, and `error` rows with no plan provenance to `skipped`. They remain visible and can be deliberately adopted through a controlled error/recent plan. Existing `ready` reports and owner decisions are preserved.

`AI_QUALITY_ENABLED=false` remains the production default until a single-target smoke is explicitly approved. This PR does not enable the worker and does not start a batch.

## Safety properties

- no implicit `all media_files -> pending` path;
- no plan means no new global queue rows;
- exact ids are frozen at plan creation, so plan/start does not recompute a larger candidate set;
- plans expire after 15 minutes;
- wrong owner, expired plan, and already-started plan fail closed;
- already ready/processing media are not overwritten at plan start;
- semantic retries are isolated from global quality operations.

## Validation

Targeted tests cover dry-run planning, exact-id start, owner mismatch, migration quarantine, callback acknowledgment ordering, and PostgreSQL isolation of quality vs semantic retry state.

Required PR gates before merge:

- project notes contract;
- type check;
- test shards and unit-test aggregate;
- Docker build;
- security supply chain;
- branch protection contract.

## Not in this slice

- enabling production `AI_QUALITY_ENABLED`;
- automatic execution after plan start;
- mass backfill approval;
- downstream typed timeout/cancel/OOM handling;
- three-model runtime switching;
- cloud escalation.

Next slice after merge: typed timeout/cancellation/retry semantics, then continue #630 three-model routing.
