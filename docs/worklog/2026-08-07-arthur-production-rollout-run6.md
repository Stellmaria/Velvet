# Arthur production rollout run 6: deploy succeeded, post-deploy bridge truncated

- Date: 2026-08-07
- Scope: Arthur Librarian Phase 2 production acceptance (#586)
- Workflow run: `31190120224`
- Rollout merge SHA: `3696e266bae37b5df13bc90317fc5237d6d41ea5`
- Verified application source: `e6571062af2c963297c17f94685490fa054c90ca`
- Verified immutable image: `ghcr.io/stellmaria/velvet@sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`

## Evidence

Run 6 passed full-history checkout, immutable target/credential preflight, and the bounded legacy backup ownership repair. The repair normalized the intended backup ownership/mode contract and reported `files=38`.

Canonical `deploy/server/deploy.sh` then executed successfully using the verified application source/image pair. It created and verified a pre-deploy PostgreSQL dump (`migrations=92`, `tables=105`, `characters=96`), reset the application checkout to the verified source commit, pulled the exact immutable image digest, started the core services and bot, and passed server smoke. The log explicitly reported `Velvet deployment succeeded: e6571062af2c963297c17f94685490fa054c90ca`.

Production therefore was changed by run 6. This is no longer a pre-deploy failure case.

## Missing post-deploy acceptance

Despite the Actions step concluding `success`, the job log contains no `reconcilectl` submit/wait output and no final `Arthur production rollout verified ...` marker. Execution ends immediately after the canonical deploy output and proceeds to credential-payload cleanup.

The rollout bridge was supplied to the remote shell as stdin via `ssh ... bash -s < .github/ops/arthur-production-rollout.sh`. The canonical deploy launched inside that streamed bridge inherited the same stdin. A child command in the deploy path could therefore consume the unread remainder of the bridge, causing the parent `bash -s` to reach EOF after the deploy and exit successfully without executing checkout restoration, fixed-target Librarian reconcile, or Arthur health checks.

Accordingly run 6 is **not** Arthur production acceptance. The deployed application image is verified and healthy, but the final production checkout is not yet accepted as the rollout merge SHA and the Arthur stack/reconcile checks from the bridge must be rerun and evidenced.

## Bounded fix

The next rollout workflow transfers the exact checked-out bridge into a private temporary file on the production host and executes that file with stdin redirected from `/dev/null`. This separates script transport from execution so canonical deploy commands cannot consume the remaining bridge body. The remote script and credential payload are both removed in the workflow's unconditional cleanup step.

The application source/image pair is unchanged. No mass enqueue, auto-enqueue, vision scope, cloud/provider use, or alternative deployment path is introduced. The next rollout still uses canonical `deploy/server/deploy.sh` followed by the existing fixed-target Librarian reconcile and Arthur runtime checks.
