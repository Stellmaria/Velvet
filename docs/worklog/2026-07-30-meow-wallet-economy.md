# Meow wallet economy

Issue: #394

This stacked change is based on `agent/meow-runtime-module` and implements the first economy stage.

## Implemented

- workspace-scoped Auf wallets;
- immutable wallet ledger;
- exact integer storage with `1 Auf = 10,000 units`;
- default economy settings: `$0.02` provider coverage and `$0.03` retail price per Auf;
- package quotes for 40, 100, 250, 500, 1,000 and 2,500 Auf;
- RUB conversion from the stored billing rate with human-friendly rounding;
- owner wallet screen with available, reserved, 30-day spend and history;
- Stell-only quick grants and wallet freeze/unfreeze;
- idempotent ledger changes and negative-balance protection;
- unit and PostgreSQL integration tests.

## Deliberately deferred

- task reserve/capture/release/refund lifecycle;
- price-version catalog per model and generation parameters;
- purchase invoices and payment confirmation;
- reconciliation worker.

Those follow after the photo capability flow is reconciled with the runtime branch, so the economy attaches to one final confirmation and task lifecycle instead of duplicating both competing implementations.
