# ADR-0001: Host launcher and disposable Docker sandbox for Hermes Codex runs

- Status: accepted for implementation and staged rollout
- Date: 2026-08-05
- Issue: #594

## Context

The canonical Hermes coder chain combined a long-lived unprivileged Docker
runner with nested bubblewrap. On the production host, user and mount namespace
creation conflicts with Docker masked/read-only paths and AppArmor mediation.
The canonical service therefore fails its own smoke and production still depends
on a compatibility override.

The existing control plane remains authoritative:

- the central router selects project, tier and route;
- the runner creates a disposable remote clone per run;
- the runner owns terminal state, fallback policy, cancellation and ledger;
- the runner records HEAD, refs, working-tree and base-checkout mutation evidence;
- Velvet and Max remain separate project identities.

Removing nested bwrap inside the existing long-lived runner without another
per-run boundary would expose Codex auth, ledgers and sibling workspaces to the
current task. That simplification is rejected.

## Decision

Docker becomes the single process sandbox boundary. A narrow root-owned host
launcher creates one disposable container for every Codex attempt.

The long-lived runner communicates over a systemd-owned Unix socket. The
launcher accepts an exact JSON schema and computes all host paths, images,
mounts, environment variables and Docker arguments. The caller cannot provide
an arbitrary command, image, mount, network, UID or host path.

The launcher is not responsible for routing, retry, workspace creation, ledger
state or mutation policy decisions. It executes one classified attempt and
returns the existing bounded result contract:

```text
returncode, stdout, stderr, cancelled, execution_started
```

`execution_started` is computed before output truncation so model/provider retry
remains fail-closed after any tool or file execution evidence.

Inside the disposable container, Codex uses `danger-full-access` because Docker
is the outer and only sandbox. This flag grants no host access. The container
receives only the current run workspace, a read-only source Codex home copied
through an explicit file allowlist into tmpfs, route-scoped credentials, a
fixed dedicated egress network and an enforcing AppArmor profile.

## Security contract

The launcher validates:

- peer UID is root or the fixed unprivileged runner UID;
- exact `run_id`, project, model, route and mutation policy enums;
- exact effective workspace path for the run;
- a non-symlink prepared checkout below the project-specific run root;
- bounded prompt and timeout;
- fixed project image and dedicated network;
- fixed installed entrypoint and project Codex home;
- route-scoped environment allowlist.

The disposable container has:

- UID/GID `10000:10000`;
- read-only root filesystem;
- `cap_drop=ALL`;
- `no-new-privileges`;
- Docker default seccomp;
- enforcing `hermes-codex-run` AppArmor;
- `--pull=never`, no log driver and no shared IPC namespace;
- only the current workspace mounted, read-only or writable by policy;
- subscription auth only for the subscription route;
- exactly one selected Byesu credential only for the provider route;
- no sibling workspaces, runner ledger, base checkout, production volumes,
  Telegram token, Runs API key or Docker socket.

The long-lived runner uses `hermes-codex-runner`, can write only its run tree,
can read the immutable base and Codex home, and can communicate with the launcher
socket. It cannot execute Codex through the canonical configuration without the
launcher.

Launcher code is installed root-owned under
`/usr/local/lib/hermes-sandbox-launcher`. It is not executed from a mutable
release worktree. The launcher uses the dedicated Docker network
`hermes-sandbox-egress`, not application or database networks.

## Compatibility

The HTTP Runs API, central router payloads, tier selection, provider order,
terminal states, structured output, cancellation semantics, workspace lifecycle
and mutation audit remain unchanged. Only process creation and cancellation are
replaced.

An explicit `CODEX_EXECUTION_BACKEND=local` rollback implementation remains
temporarily, but it additionally requires `HERMES_ALLOW_LOCAL_ROLLBACK=1`.
Canonical Compose sets neither local backend nor rollback gate. There is no
automatic downgrade when the launcher is unavailable.

The existing compatibility override remains available only for controlled
rollback until production acceptance completes. It is not part of the new
canonical Compose contract and must never be selected automatically.

## Consequences

Benefits:

- no nested namespace dependency;
- per-run isolation from auth, ledgers and sibling workspaces;
- small and testable privileged surface;
- bounded cancellation and stale-container cleanup;
- preserved router, fallback and mutation-audit behavior.

Costs:

- Docker container startup for every attempt;
- root-owned launcher and AppArmor profiles must be installed atomically;
- production rollout requires socket, network and image preflight before canary;
- reboot and rollback behavior require live evidence.

## Rejected alternatives

### Keep debugging nested bwrap

Rejected because the security model depends on host, Docker and AppArmor
namespace interactions that already fail on the target host and require broader
privileges to make portable.

### Remove bwrap and run Codex in the long-lived runner

Rejected because a task would retain access to persistent Codex home, ledger and
sibling workspaces. Docker would isolate the project from the host, but not one
task from another.

### Give the runner Docker socket access

Rejected because Docker socket access is effectively host control and would put
the privileged boundary inside the model-facing container.

### Run launcher code from the active Git checkout

Rejected because updating a mutable checkout would implicitly update root-run
code. Launcher artifacts are copied to a root-owned fixed install directory and
activated through systemd only after validation.
