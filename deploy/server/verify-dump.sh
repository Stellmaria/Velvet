#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-.env.server}"
COMPOSE_FILE="${VELVET_COMPOSE_FILE:-docker-compose.server.yml}"
DUMP_PATH="${1:-}"

if [[ -z "$DUMP_PATH" ]]; then
  echo "Usage: verify-dump.sh /absolute/or/relative/path.dump" >&2
  exit 2
fi

cd "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing server env file: $APP_DIR/$ENV_FILE" >&2
  exit 2
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing Compose file: $APP_DIR/$COMPOSE_FILE" >&2
  exit 2
fi
if [[ ! -s "$DUMP_PATH" ]]; then
  echo "PostgreSQL dump is missing or empty: $DUMP_PATH" >&2
  exit 2
fi

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
restore_database="velvet_restore_check_$(date -u +%Y%m%d%H%M%S)_$RANDOM"
created=0

cleanup() {
  if [[ "$created" == "1" ]]; then
    "${compose[@]}" exec -T postgres sh -ceu '
      dropdb --force --if-exists -U "$POSTGRES_USER" "$1"
    ' sh "$restore_database" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

"${compose[@]}" up -d postgres

# Проверяем, что архив читается pg_restore до создания временной базы.
"${compose[@]}" exec -T postgres pg_restore --list < "$DUMP_PATH" >/dev/null

"${compose[@]}" exec -T postgres sh -ceu '
  createdb -U "$POSTGRES_USER" -T template0 "$1"
' sh "$restore_database"
created=1

"${compose[@]}" exec -T postgres sh -ceu '
  pg_restore --exit-on-error --no-owner --no-privileges \
    -U "$POSTGRES_USER" -d "$1"
' sh "$restore_database" < "$DUMP_PATH"

verification_query="SELECT
  (SELECT COUNT(*) FROM schema_migrations)::TEXT || '|' ||
  (SELECT COUNT(*) FROM information_schema.tables
   WHERE table_schema='public' AND table_type='BASE TABLE')::TEXT || '|' ||
  (SELECT COUNT(*) FROM characters)::TEXT;"
verification="$(
  "${compose[@]}" exec -T postgres sh -ceu '
    psql -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$1" -c "$2"
  ' sh "$restore_database" "$verification_query"
)"

IFS='|' read -r migration_count table_count character_count <<< "${verification//$'\r'/}"
if [[ ! "$migration_count" =~ ^[0-9]+$ ]] || (( migration_count < 1 )); then
  echo "Restore verification failed: schema_migrations is empty." >&2
  exit 1
fi
if [[ ! "$table_count" =~ ^[0-9]+$ ]] || (( table_count < 1 )); then
  echo "Restore verification failed: no public tables found." >&2
  exit 1
fi
if [[ ! "$character_count" =~ ^[0-9]+$ ]]; then
  echo "Restore verification failed: characters count is invalid." >&2
  exit 1
fi

printf 'Verified dump: migrations=%s tables=%s characters=%s\n' \
  "$migration_count" "$table_count" "$character_count"
