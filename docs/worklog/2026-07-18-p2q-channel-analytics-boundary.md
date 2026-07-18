# P2Q channel analytics ingest boundary

- Date: 2026-07-18
- Status: complete
- Branch: `agent/p2q-channel-analytics-boundary`
- Base: `c2b82a3f053d3e324c9f15f43c60904c96aa2341`

## Before

### Goal
Isolate channel analytics ingest failures from the Telegram update.

### Baseline
43 unresolved broad exceptions.

### Scope
One approved marker, behavior tests, inventory, and project notes.

### Completion criteria
Ingest failures are reported with channel context, cancellation propagates, untracked channels skip ingest, and CI passes.

## After

### Completed
The channel ingest boundary is classified. Baseline changed from 43 to 42.

### Compatibility
No migration, analytics query, or routing changes.

### Checks
Tests, Docker build, and project notes contract.

### PR
PR is created after inventory generation.

### Remaining
42 unresolved broad exceptions.

### Next
First target from the current AST inventory.
