# Production deployment commands

Этот файл является кратким источником точных команд для VPS. Подробные причины, smoke-последовательность и rollback описаны в `docs/SERVER_PRODUCTION_RUNBOOK.md`.

## 1. Пользователь и каталоги

Dockerfile запускает bot под UID/GID `10001`, поэтому host-пользователь `velvet` создаётся с теми же ID. Тогда host deploy и bot-контейнер могут безопасно писать в общие bind directories без `chmod 777`.

```bash
sudo useradd --uid 10001 --user-group --create-home --shell /bin/bash velvet
sudo usermod -aG docker velvet
sudo install -d -o 10001 -g 10001 -m 0750 /srv/velvet
sudo install -d -o 10001 -g 10001 -m 0750 \
  /srv/velvet/data \
  /srv/velvet/data/backups \
  /srv/velvet/data/logs \
  /srv/velvet/data/runtime \
  /srv/velvet/data/hermes
```

PostgreSQL использует named volume `velvet-postgres-data`; каталог `/srv/velvet/data/postgres` создавать и `chown` не требуется.

## 2. Checkout и secrets

```bash
sudo -u velvet git clone https://github.com/Stellmaria/Velvet.git /srv/velvet
cd /srv/velvet
sudo -u velvet cp .env.server.example .env.server
sudo -u velvet cp .env.hermes.example .env.hermes
sudo chmod 600 .env.server .env.hermes
```

Заполнить `.env.server`, затем:

```bash
sudo -u velvet python3 /srv/velvet/scripts/server_preflight.py \
  --env-file /srv/velvet/.env.server \
  --hermes-env /srv/velvet/.env.hermes \
  --create-directories
```

## 3. Первый PostgreSQL restore

```bash
cd /srv/velvet
sudo -u velvet docker compose --env-file .env.server \
  -f docker-compose.server.yml up -d postgres

sudo -u velvet docker compose --env-file .env.server \
  -f docker-compose.server.yml exec -T postgres sh -ceu '
    pg_restore --exit-on-error --no-owner --no-privileges \
      -U "$POSTGRES_USER" -d "$POSTGRES_DB"
  ' < /srv/velvet/data/backups/velvet-final.dump

sudo -u velvet bash deploy/server/verify-dump.sh \
  /srv/velvet/data/backups/velvet-final.dump
```

## 4. Первый bot start

```bash
cd /srv/velvet
sudo -u velvet docker compose --env-file .env.server \
  -f docker-compose.server.yml build --pull bot
sudo -u velvet docker compose --env-file .env.server \
  -f docker-compose.server.yml up -d postgres bot
sudo -u velvet docker compose --env-file .env.server \
  -f docker-compose.server.yml exec -T bot \
  python scripts/server_smoke.py
```

## 5. systemd

```bash
sudo cp deploy/systemd/velvet-compose.service \
  /etc/systemd/system/velvet-compose.service
sudo systemctl daemon-reload
sudo systemctl enable --now velvet-compose.service
```

## 6. Subsequent deploy

```bash
sudo -u velvet env \
  VELVET_APP_DIR=/srv/velvet \
  VELVET_ENV_FILE=.env.server \
  VELVET_COMPOSE_FILE=docker-compose.server.yml \
  bash /srv/velvet/deploy/server/deploy.sh
```

`deploy.sh` не меняет код, пока custom-format dump не восстановлен в disposable database. Database rollback никогда не выполняется автоматически.
