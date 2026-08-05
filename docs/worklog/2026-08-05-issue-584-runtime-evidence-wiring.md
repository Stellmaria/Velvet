# Issue #584: runtime evidence wiring after readiness gate

Date: 2026-08-05

## Scope

This repository-only follow-up to PR #640 wires the merged readiness/evidence
contract into the canonical launcher-backed runtime. It performs no server
operation, deployment, restart or production migration.

## Changes

- Added a narrow launcher subclass that preserves the existing tier routing,
  provider fallback and Git mutation audit while recording:
  - effective `process_cwd`;
  - final Git branch;
  - top-level `execution_started`;
  - initial `push_or_pr_observed=false`.
- Execution evidence is derived from actual tool/file events or trusted launcher
  state. Lifecycle events alone do not count.
- The existing tier runner remains the sole mutation authority. The adapter does
  not write `mutation_started`; successful mutation remains derived only from
  Git/base changes or push/PR evidence.
- Added an evidence-aware tier router that preserves the existing typed routing
  contract and attaches the complete paginated PR changed-file list.
- PR evidence fails closed when the file count changes during the snapshot or
  exceeds the supported GitHub pagination bound.
- Updated exact-release mounts, runtime import guard, systemd readability gate,
  operator image and orchestration entrypoints.

## Safety boundary

- No Docker socket, systemd, host command, arbitrary GitHub path or production
  credential is exposed to model-facing code.
- Router GitHub paths remain fixed by code and reject query/path traversal from
  callers.
- The canonical launcher remains the only process-execution boundary.
- Compatibility/local execution remains available only through the pre-existing
  explicit rollback gate and is not selected by canonical Compose.

## Acceptance

Focused tests cover execution-vs-mutation separation, exact runtime mounts and
import graph, typed tier handoff, paginated changed-file evidence, deterministic
file ordering and fail-closed count drift.
