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

The release does not restart the Velvet bot, PostgreSQL, supervisor, Krita, chat
agents, database proxies or the coder router. It does not run migrations or submit
a production coder task.

Detached release worktrees must remain present while containers bind-mount files
from them. Old worktree retention is a separate maintenance operation and must
never remove the target referenced by `/srv/hermes-coders/releases/current-hermes-coders`.
