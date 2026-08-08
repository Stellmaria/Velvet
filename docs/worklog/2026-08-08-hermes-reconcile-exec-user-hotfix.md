# Hermes reconcile exec-user hotfix

## Scope

Production validation of the Librarian reconcile rollout exposed a false installer failure after the reconcile host bridge and gateway had already installed successfully. `docker compose exec -T hermes` reported uid/gid `0:0` because the Hermes container is configured to start as root for s6-overlay bootstrap, while the mounted Hermes data directory and `reconcilectl.py` are owned by the remapped Hermes runtime uid/gid.

The installer incorrectly treated the default `docker compose exec` uid as proof that the runtime privilege model was wrong.

## Fix

- keep the Hermes container bootstrap model unchanged;
- keep the reconcile client owned and mode `0500` by the Hermes data owner;
- execute the installer acceptance check explicitly with `docker compose exec --user "$hermes_uid:$hermes_gid"`;
- verify both uid and gid through `EXPECTED_UID` / `EXPECTED_GID`;
- run `reconcilectl.py --help` under that same unprivileged identity;
- add a regression contract that forbids the old hard-coded `id -u == 10000` check.

## Production evidence

On production at source `8b160db820592c36f51da491b0525754f6954bdf`:

- `hermes-operator-reconcile.service` was active;
- `hermes-reconcile-gateway.service` was active and reachable from Hermes;
- the reconcile socket existed with the expected group permissions;
- the installed PrivateTmp/TMPDIR fix was present;
- `/opt/data/tools/reconcilectl.py` was executable and owned by uid/gid `10000:10000`;
- `python /opt/data/tools/reconcilectl.py --help` returned `0`;
- only the default `docker compose exec` identity was root, which caused the installer false negative;
- Storage Librarian auto enqueue and full-archive backfill remained disabled during diagnosis.

## Safety

This hotfix does not change Librarian scheduling, queue semantics, inference routing, Docker privileges, systemd sandboxing, or the Hermes runtime user model. It only makes the installer verify the reconcile client under the actual mounted-data owner identity.
