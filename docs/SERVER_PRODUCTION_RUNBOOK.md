# Velvet production migration runbook

## 1. Граница этого runbook

Этот документ переносит на Linux VPS текущий репозиторий `Stellmaria/Velvet`:

- Velvet Bot;
- PostgreSQL;
- AI task queue, budget ledger и background workers;
- optional Hermes Agent после отдельной проверки.

Второй Telegram-бот не добавляется фиктивным сервисом. Для него необходимы реальные repository URL, Dockerfile/command, `.env.example`, схема PostgreSQL и backup policy. До получения этих данных он переносится отдельным stack или Compose override.

## 2. Целевые пути

```text
/srv/velvet/                  checkout репозитория
/srv/velvet/.env.server       production env Velvet
/srv/velvet/.env.hermes       отдельный env Hermes
/srv/velvet/data/postgres     PostgreSQL volume
/srv/velvet/data/backups      custom-format PostgreSQL dumps
/srv/velvet/data/logs         application logs
/srv/velvet/data/runtime      runtime state
/srv/velvet/data/hermes       Hermes persistent volume
```

Production secrets не хранятся в Git, Telegram, issue, PR, диагностических ZIP или model context.

## 3. Подготовка VPS

Рекомендуемый первый профиль без локального инференса:

- Ubuntu 24.04 LTS;
- 8 vCPU;
- 24 ГБ RAM;
- 200 ГБ NVMe;
- Docker Engine и Compose plugin;
- отдельный пользователь `velvet` без root login;
- SSH только по ключу;
- PostgreSQL без публичного порта.

Создание каталогов:

```bash
sudo useradd --create-home --shell /bin/bash velvet
sudo usermod -aG docker velvet
sudo install -d -o velvet -g velvet -m 0750 /srv/velvet
sudo install -d -o 10001 -g 10001 -m 0750 \
  /srv/velvet/data/backups \
  /srv/velvet/data/logs \
  /srv/velvet/data/runtime
sudo install -d -o 999 -g 999 -m 0700 /srv/velvet/data/postgres
sudo install -d -o velvet -g velvet -m 0750 /srv/velvet/data/hermes
```

UID PostgreSQL в конкретном image проверяется перед первым запуском. Если container сообщает permission denied, исправляется владелец только каталога `data/postgres`, а не всего `/srv/velvet`.

Firewall:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw enable
```

Telegram long polling не требует публичного HTTP-порта. PostgreSQL не публикуется. Hermes gateway при включении доступен только на `127.0.0.1:8642`.

## 4. Checkout и env

```bash
sudo -u velvet git clone https://github.com/Stellmaria/Velvet.git /srv/velvet
cd /srv/velvet
sudo -u velvet cp .env.server.example .env.server
sudo -u velvet cp .env.hermes.example .env.hermes
sudo chmod 600 .env.server .env.hermes
```

На первом запуске обязательны:

```env
AI_TEXT_ENABLED=false
AI_VISION_ENABLED=false
AI_VISION_QUEUE_ENABLED=false
KIE_ENABLED=false
HERMES_INCIDENT_ENABLED=false
CODEX_ENABLED=false
KRITA_WATERMARK_ENABLED=false
```

Заполнить минимум:

- `BOT_TOKEN`;
- `ALLOWED_USER_IDS` числовым ID владельца;
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`;
- `DATABASE_URL` с host `postgres` и тем же паролем;
- `STORAGE_ENCRYPTION_SECRET`;
- `SUPERVISOR_TOKEN`;
- Telegram Storage IDs, если storage уже используется.

Проверка до запуска:

```bash
cd /srv/velvet
python3 scripts/server_preflight.py \
  --env-file .env.server \
  --hermes-env .env.hermes \
  --create-directories

docker compose --env-file .env.server \
  -f docker-compose.server.yml config --quiet
```

Preflight не печатает значения секретов. Любой placeholder, слабый secret, `localhost` в `DATABASE_URL`, включённая модель без цены или опасный feature flag блокирует запуск.

## 5. Финальный локальный dump

На старом компьютере:

1. остановить локальный бот и Supervisor;
2. убедиться, что polling-процесс больше не работает;
3. создать финальный custom-format dump;
4. сохранить SHA-256 файла;
5. передать файл на VPS через `scp`/SFTP.

Пример:

```bash
pg_dump --format=custom --no-owner --no-privileges \
  --dbname "$DATABASE_URL" \
  --file velvet-final.dump
sha256sum velvet-final.dump > velvet-final.dump.sha256
scp velvet-final.dump velvet-final.dump.sha256 velvet@SERVER:/srv/velvet/data/backups/
```

На VPS:

```bash
cd /srv/velvet/data/backups
sha256sum --check velvet-final.dump.sha256
chmod 600 velvet-final.dump velvet-final.dump.sha256
```

## 6. Первый restore

Запустить только PostgreSQL:

```bash
cd /srv/velvet
docker compose --env-file .env.server \
  -f docker-compose.server.yml up -d postgres
```

Для пустого production volume восстановить финальный dump:

```bash
docker compose --env-file .env.server \
  -f docker-compose.server.yml exec -T postgres sh -ceu '
    pg_restore --exit-on-error --no-owner --no-privileges \
      -U "$POSTGRES_USER" -d "$POSTGRES_DB"
  ' < /srv/velvet/data/backups/velvet-final.dump
```

Если база уже содержит объекты, не использовать `--clean` вслепую. Создать новый пустой volume или отдельную БД, проверить dump и только затем переключить приложение.

Полная проверка того же файла в одноразовой БД:

```bash
cd /srv/velvet
bash deploy/server/verify-dump.sh \
  /srv/velvet/data/backups/velvet-final.dump
```

Скрипт:

- проверяет формат через `pg_restore --list`;
- создаёт БД только с префиксом `velvet_restore_check_`;
- полностью восстанавливает dump;
- проверяет `schema_migrations`, количество таблиц и персонажей;
- удаляет одноразовую БД через `dropdb --force`.

## 7. Первый запуск Velvet без AI

```bash
cd /srv/velvet
docker compose --env-file .env.server \
  -f docker-compose.server.yml build --pull bot

docker compose --env-file .env.server \
  -f docker-compose.server.yml up -d postgres bot

docker compose --env-file .env.server \
  -f docker-compose.server.yml ps
```

Read-only/temporary smoke:

```bash
docker compose --env-file .env.server \
  -f docker-compose.server.yml exec -T bot \
  python scripts/server_smoke.py
```

Smoke проверяет:

- подключение и write-транзакцию PostgreSQL через temporary table;
- наличие миграций;
- критичные таблицы, включая `ai_task_batches`;
- доступность backup directory;
- Telegram `getMe` без вывода token;
- состояние AI pause и активной очереди.

Затем вручную проверить в Telegram:

1. `/start` и главное меню;
2. `/system` и `/version`;
3. публичный и личный архив;
4. сохранение и выдачу одного изображения;
5. публикацию тестового черновика;
6. Telegram Storage upload/download;
7. `/ai_budget` и `/ai_queue` при выключенных моделях;
8. рестарт bot-контейнера и сохранность состояния.

## 8. systemd-автозапуск

```bash
sudo cp /srv/velvet/deploy/systemd/velvet-compose.service \
  /etc/systemd/system/velvet-compose.service
sudo systemctl daemon-reload
sudo systemctl enable --now velvet-compose.service
sudo systemctl status velvet-compose.service
```

Unit запускает preflight и `docker compose config --quiet` до старта. Hermes не включается автоматически этим unit.

## 9. Поэтапное включение AI

Не включать несколько новых контуров одновременно.

### 9.1 RP

1. заполнить model ID, API key и цены;
2. выполнить preflight;
3. установить `AI_TEXT_ENABLED=true`;
4. перезапустить bot;
5. проверить `/rp_status`, одну сцену и продолжение после рестарта;
6. проверить `/ai_usage` и стоимость хода.

### 9.2 Одиночный VL

1. настроить Flash route и цены;
2. оставить `AI_VISION_QUEUE_ENABLED=false`;
3. включить `AI_VISION_ENABLED=true`;
4. проверить одно обычное изображение;
5. повторить то же изображение и подтвердить cache hit;
6. отдельно проверить Pro и sensitive fallback;
7. проверить журнал расходов.

### 9.3 VL batch queue

После одиночного smoke:

```env
AI_VISION_QUEUE_ENABLED=true
```

Порядок:

```text
/ai_batch_plan 10
/ai_batch_start UUID
/ai_batch_status UUID
```

Первая партия ограничивается десятью изображениями. Только после проверки результатов, расходов, retry и cache размер увеличивается.

### 9.4 Kie / «Мяу»

1. проверить model IDs в кабинете Kie;
2. задать `KIE_USD_TO_RUB`;
3. заполнить API key;
4. выполнить preflight;
5. установить `KIE_ENABLED=true`;
6. выполнить одну недорогую генерацию;
7. проверить result delivery, `/ai_usage` и retry.

## 10. Hermes

Hermes использует отдельный Telegram bot token и отдельный `.env.hermes`.

До запуска:

- `TELEGRAM_ALLOWED_USERS` содержит только ID владельца;
- `API_SERVER_KEY` совпадает с `HERMES_API_KEY` в `.env.server`;
- Telegram token Hermes не совпадает с `BOT_TOKEN` Velvet;
- GitHub token имеет доступ только к `Stellmaria/Velvet`;
- image закреплён конкретным tag/digest;
- отсутствуют mounts production `.env`, PostgreSQL, bot checkout и Docker socket.

Запуск:

```bash
cd /srv/velvet
python3 scripts/server_preflight.py \
  --env-file .env.server --hermes-env .env.hermes

docker compose --env-file .env.server \
  -f docker-compose.server.yml --profile agent up -d hermes
```

После отдельного smoke устанавливается `HERMES_INCIDENT_ENABLED=true` и перезапускается bot.

## 11. Подтверждаемый deploy

Для последующих обновлений:

```bash
sudo -u velvet env \
  VELVET_APP_DIR=/srv/velvet \
  VELVET_ENV_FILE=.env.server \
  VELVET_COMPOSE_FILE=docker-compose.server.yml \
  bash /srv/velvet/deploy/server/deploy.sh
```

Deploy:

1. блокирует параллельный запуск;
2. выполняет preflight;
3. отказывается работать с tracked local changes;
4. создаёт custom-format pre-deploy dump;
5. полностью восстанавливает dump в одноразовую БД;
6. обновляет код только после успешной проверки backup;
7. строит новый image и ждёт healthcheck;
8. запускает server smoke;
9. при ошибке откатывает код и bot image;
10. никогда не восстанавливает старую БД автоматически.

Hermes при deploy запускается только при явном `VELVET_START_HERMES=1`.

## 12. Rollback

### Код

Deployment script автоматически возвращает предыдущий commit и перестраивает bot image, если новый контейнер не прошёл health/smoke.

Ручной откат:

```bash
cd /srv/velvet
git reset --hard PREVIOUS_SHA
docker compose --env-file .env.server \
  -f docker-compose.server.yml build bot
docker compose --env-file .env.server \
  -f docker-compose.server.yml up -d postgres bot
```

### База

База не откатывается автоматически. Перед ручным restore:

1. остановить bot;
2. сделать dump текущего состояния;
3. проверить выбранный backup через `verify-dump.sh`;
4. восстановить в отдельную БД;
5. сравнить counts;
6. только затем переключить `DATABASE_URL` или production DB.

## 13. Когда отключать локальный компьютер

Локальный контур сохраняется до выполнения всех условий:

- server smoke полностью пройден;
- VPS пережил reboot;
- systemd автоматически поднял stack;
- выполнены минимум три успешных server backup-цикла;
- один server dump полностью восстановлен;
- RP и одиночный VL проверены;
- Telegram Storage доступен;
- rollback к предыдущему commit проверен.

Только после этого отключаются Windows Supervisor и Ollama autostart. Локальная БД и последние backups не удаляются до стабильного контрольного периода.
