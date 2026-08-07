# Hermes reboot persistence fixes

## Summary

- Let systemd recreate `/run/hermes-sandbox-private` with mode `0700` for the sandbox launcher.
- Persist the executable bit for `deploy/hermes-entities/reconcile.sh`.
- Add deployment-contract regression coverage for both behaviors.

## Motivation

A production reboot exposed two persistence gaps. The entity reconcile unit failed with `203/EXEC` because the reconciler checkout was not executable, and the sandbox launcher failed with `226/NAMESPACE` because the volatile `/run/hermes-sandbox-private` directory was absent before systemd applied `ReadWritePaths=`.

## Validation

- `systemd-analyze verify` passes for the launcher unit with dependency stubs.
- Deployment-contract tests cover the runtime directory and executable-mode contracts.
- Post-reboot production checks confirmed authenticated launcher probes, coder gateways, router, and application services healthy.
