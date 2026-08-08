# Arthur Librarian

Arthur is the dedicated owner-only Telegram interface for the existing Storage
Librarian. Archive processing remains explicit: environment-driven AFK enqueue is
disabled, while the owner can start or stop a cooperative full-archive loop from
the Arthur Telegram bot.

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
  `/archive start` does not change that environment flag; it explicitly drives
  `enqueue_pending()` inside the already running owner-only Arthur process.
- A running Storage analysis cannot be reset to `queued` by another manual
  `/analyze` request.
- Archive and manual `/analyze` inference share one application lock, so Arthur
  does not intentionally run two local Storage analyses in parallel.

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
- `/archive start`
- `/archive stop`
- `/archive status`
- `/analyze ID`
- `/result ID`
- `/ask вопрос`
- `/digest [дни]`
- `/queue`
- `/download ID`
- `/help`

`/archive start` starts a full-archive loop for the currently configured
`STORAGE_LIBRARIAN_ANALYZER_VERSION`. It gradually calls `enqueue_pending()` and
processes one Storage job per cycle using the configured Librarian scan interval.
Objects that already have a completed analysis for the same analyzer version are
not reprocessed. A deliberate full rescan therefore still uses a new analyzer
version, preserving previous results until each object is replaced by the new
analysis.

`/archive stop` is cooperative. It does not cancel Ollama in the middle of an
object and does not mutate Docker state. If an object is currently running,
Arthur finishes that object and then exits the archive loop. Queue rows and
stored analyses remain in PostgreSQL, so `/archive start` can resume later.

`/archive status` shows whether the loop is running, stopping or stopped,
current queue counters, analyzer version and the last loop-level error if one
was observed.

`/cancel` remains intentionally absent for individual inference. Cooperative
archive stop is safe because it waits for the current Storage job boundary.

## Production acceptance

Confirm that Telegram `/archive status` initially reports `stopped`. Run
`/archive start`, verify that the state becomes `running` and queue counters move,
then run `/archive stop` and confirm the state becomes `stopping` or `stopped`
without Docker pause/restart activity. After the current object boundary, status
must settle on `stopped` while Arthur itself remains healthy.

Also verify one loaded Ollama model, no host binding for `11434`, and
`STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`.
