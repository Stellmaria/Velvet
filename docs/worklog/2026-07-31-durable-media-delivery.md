# Durable media delivery

Issue: #457

## Problem

Provider success and financial completion previously happened before best-effort Telegram delivery. A CDN or Telegram outage could therefore leave a paid generation without a durable delivery state, while the active implementation depended on installer order and worker monkeypatches.

## Implementation

- Added durable `media_delivery_jobs` and `media_delivery_items` state with independent result resolution, download, original, preview and notification outcomes.
- Added provider-neutral application use cases: `ResolveProviderResult`, `DeliverMediaResult` and `RedeliverMediaResult`.
- Added PostgreSQL, provider-result, HTTP download and Telegram delivery adapters.
- All generation slots reuse one process-level delivery runtime; database claims serialize recovery work.
- Generation workers register provider success and delegate result delivery to the durable use cases.
- Restart recovery reuses the saved provider task ID and never submits a replacement paid generation.
- Explicit redelivery checks workspace/user ownership and cannot call provider submit or charging paths.
- The existing composition stage names remain during rollout, but their legacy delivery installers are neutralized and `_deliver_best_effort` cannot override the canonical pipeline. Their physical removal is deferred to the broader installer cleanup in #455.

## Outcomes

- Original and preview delivery are independent and durable.
- Missing provider URLs are resolved later from the existing provider task.
- HTTP 404/410 is recorded as an explicit expired result.
- Telegram/CDN failures are retried with persisted attempts and errors.
- Structured resolution and delivery outcome logs are emitted best-effort for observability.
