# Arthur Librarian

Arthur is the dedicated owner-only Telegram interface for the existing Storage
Librarian. Phase 2 does not enable archive batches, AFK processing or vision.

## Security boundary

- `ARTHUR_BOT_TOKEN` is a separate Telegram bot identity and must not equal
  Velvet `BOT_TOKEN`.
- Telegram `file_id` values are bot-scoped. Existing Storage parts therefore
  remain downloadable only through `arthur-storage-gateway`, which receives the
  Velvet token and exposes a private authenticated byte contract.
- The Arthur container receives neither `BOT_TOKEN`, GitHub credentials, Docker
  socket, shell/systemd tools nor cloud provider keys.
- Arthur, gateway, Ollama and Librarian Hermes publish no host ports.
- `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` is enforced both by settings and Compose.
- A running Storage analysis cannot be reset to `queued` by another manual
  `/analyze` request.

## Required secrets

Copy the variables from `deploy/hermes-librarian/.env.arthur.example` into the
server secret env. Generate `ARTHUR_STORAGE_GATEWAY_API_KEY` as at least 24
random characters. Configure either owner IDs or owner usernames.

Do not commit token values.

The installer prepares `${VELVET_DATA_DIR:-/srv/velvet/data}/arthur` directly
for container UID/GID `10001:10001`; it does not require recursive ownership
changes. Arthur sees that directory at `/app/runtime/arthur`.

## Lifecycle

The canonical update remains:

```bash
sudo docker exec velvet-hermes-1 \
  python /opt/data/tools/opsctl.py velvet update
```

The Librarian reconcile invokes `deploy/hermes-librarian/start.sh`. When Arthur
credentials are complete, it starts `arthur-storage-gateway` and `arthur`
sequentially with `--no-deps`; the already healthy Ollama and Librarian Hermes
containers are not recreated by the Arthur step. The startup gate verifies the
private authenticated Arthur-to-gateway route, gateway-to-PostgreSQL lookup,
heartbeat and a schema-bound Arthur-container-to-Ollama request. Without
complete Arthur credentials, the profile remains stopped.

Do not replace the canonical lifecycle with a direct profile-wide
`docker compose up`: doing so bypasses the sequencing and smoke gates.

## Commands

- `/start`
- `/status`
- `/analyze ID`
- `/result ID`
- `/ask вопрос`
- `/digest [дни]`
- `/queue`
- `/download ID`
- `/help`

`/cancel` is intentionally absent until cooperative cancellation can guarantee
that a running inference and its PostgreSQL state are reconciled safely.

## Production acceptance

Use one safe Storage object. Confirm the Telegram result and then query
PostgreSQL for job status, `analyzer`, `analyzer_version`, `confidence` and run
metadata. Also verify one loaded Ollama model, no host binding for `11434`, and
`STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`.

Do not remove temporary reconcile workarounds during the first Arthur rollout.
