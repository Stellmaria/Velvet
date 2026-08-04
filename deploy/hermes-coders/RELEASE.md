# Hermes coder production release

Hermes coder runtime changes are released independently from the main Velvet bot
stack. Do not use `deploy/server/deploy.sh` for a Hermes-only change: that path
updates the full production checkout and restarts bot-side services.

## Release contract

1. Merge the reviewed Hermes change and `.github/workflows/deploy-hermes-coders.yml`
   into `main` after all required checks pass.
2. Resolve the exact current `main` SHA.
3. Create the branch `release/hermes-coders-<40-character-main-sha>` at that exact
   commit, or manually dispatch the workflow from that exact `main` commit with
   `confirmation=DEPLOY_HERMES`.
4. The workflow revalidates the SHA against `origin/main` on GitHub and on the
   production host.
5. Source is mounted from a detached worktree under
   `/srv/hermes-coders/releases/<sha>`; `/srv/velvet` is not reset or cleaned.
6. Only `hermes-coder-velvet` and `hermes-coder-max` are force-recreated with
   `--no-deps --no-build`.
7. Success requires both containers to be healthy with restart count `0`,
   `init=true`, the expected mounted source SHA, the unchanged image IDs and zero
   host/container zombies.
8. Any failed verification recreates both containers from their previous Compose
   source.
9. The successful workflow atomically updates
   `/srv/hermes-coders/releases/current-hermes-coders` to the exact release.

The release does not restart the Velvet bot, PostgreSQL, supervisor, Krita, chat
agents, database proxies or the coder router. It does not run migrations or submit
a production coder task.

## One-time systemd reconciliation

The production units are release-bound. They must use:

- `/srv/hermes-coders/releases/current-hermes-coders/deploy/hermes-coders`;
- `/srv/hermes-coders/releases/current-hermes-coders/deploy/hermes-orchestration`.

After the first release containing the release-bound units, run exactly once:

```bash
release_dir="$(readlink -f /srv/hermes-coders/releases/current-hermes-coders)"
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  bash "$release_dir/deploy/hermes-coders/reconcile_release_systemd.sh"
```

The reconciler:

1. validates that the symlink resolves to a 40-character release SHA;
2. backs up installed units and known legacy overrides under
   `/var/backups/hermes-coders-systemd`;
3. installs both repository-managed unit files;
4. removes the obsolete `20-bwrap-runtime.conf` drop-in from the active systemd
   configuration while preserving its backup;
5. performs `daemon-reload`, enables the units and clears stale failed state;
6. starts or reloads the coder and router oneshot units without `compose down` and
   without deleting volumes, auth, ledger, runs, workspaces or secrets;
7. requires `active/exited/0`, runtime/provider/router smoke, healthy containers,
   restart count `0` and `init=true`;
8. retires the old manual Compose override into the backup directory only after
   all checks pass.

A failed reconciliation restores the previous unit files and force-recreates only
the two coder containers from their previously mounted Compose source. It never
uses `compose down`, removes volumes or deletes persistent coder data.

## Smoke modes

`runtime_smoke.py` always checks GitHub push authorization, ChatGPT/Codex auth,
model catalog, immutable base checkout, disposable writable run clone, AppArmor,
seccomp, `NoNewPrivs`, dropped capabilities, read-only rootfs and zombie state.

The nested bubblewrap `/proc` mount is a separate strict diagnostic because some
host AppArmor combinations reject that additional nested mount even though real
read-only and writable task sandboxes work. Enable it explicitly only for sandbox
qualification:

```bash
sudo env \
  HERMES_CODERS_ROOT=/srv/hermes-coders \
  HERMES_CODEX_STRICT_NESTED_PROC_SMOKE=1 \
  python3 /srv/hermes-coders/releases/current-hermes-coders/deploy/hermes-coders/runtime_smoke.py
```

Normal systemd startup uses `HERMES_CODEX_STRICT_NESTED_PROC_SMOKE=0`.

## Evidence contract

Every completed `deploy Hermes coders` run is followed by
`.github/workflows/report-hermes-coder-release.yml`. The reporter does not check
out or execute release-branch code. It validates that a push ref embeds the exact
workflow head SHA, reads the completed Actions log with `actions: read`, redacts
credential-like values, bounds the excerpt to the final 80 lines and comments the
outcome, commit, ref, run URL and verification tail on issue `#592`.

The reporter has only `actions: read`, `contents: read` and `issues: write`.
A failed production release produces the same evidence comment and then leaves the
reporter workflow failed, so failure cannot disappear behind a green reporting job.

Detached release worktrees must remain present while containers bind-mount files
from them. Old worktree retention is a separate maintenance operation and must
never remove the target referenced by `/srv/hermes-coders/releases/current-hermes-coders`.
