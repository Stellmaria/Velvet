# Hermes coder release runtime import graph

## Production evidence

Release `74bfb3a19506e5b2a387f4de62b711808ea88a4c` recreated both Hermes coder containers with release-bound wrapper modules but without a release-bound `codex_runner.py` mount. The containers therefore combined current wrapper files with an older image copy of `codex_runner.py` and failed during startup with:

```text
ImportError: cannot import name 'Handler' from 'codex_runner'
```

A temporary read-only production mount exposed the release file, but the detached worktree had been created under `umask 077`, leaving that file mode `0600`. Container UID `10000:10000` then failed with:

```text
PermissionError: [Errno 13] Permission denied: '/app/codex_runner.py'
```

After changing the release file to `0644` and mounting it read-only, both coder containers recovered as `running`, `healthy`, `restarts=0`.

## Fix

- Mount `codex_runner.py` and `codex_routed_runner.py` from the exact release for both coder services.
- Include both modules in `runtime_source_guard.py`, which grants only the world-read bit required by the container UID.
- Validate the complete local Python import graph before any release or systemd Compose recreation. The existing release workflow and systemd unit already invoke this guard before `docker compose up`.
- Add regression coverage for the complete canonical mount set and the import-graph preflight.

## Safety properties

- No Compose teardown or volume removal.
- No auth or data mutation.
- No AppArmor weakening.
- A mismatched runtime graph now fails before production coder containers are recreated.
