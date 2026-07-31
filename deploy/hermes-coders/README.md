# Изолированные Hermes Coder для Velvet и Romatic Club Max

Этот стек запускает два независимых Telegram-агента:

- `hermes-coder-velvet` работает только с `Stellmaria/Velvet`;
- `hermes-coder-max` работает только с `Stellmaria/romatic_club_bot_max`.

Они не монтируют production checkout, `.env`, Docker socket или PostgreSQL volume. Каждый coder получает отдельные:

- Telegram bot token;
- fine-grained GitHub token;
- Hermes data directory;
- Git workspace;
- read-only PostgreSQL роль;
- внутреннюю DB-сеть.

## Сетевая граница

Coder-контейнеры не подключаются к `velvet_backend` или `romaticclub_default` напрямую. Минимальные TCP-прокси подключены к production-сетям и публикуют только PostgreSQL `5432` во внутренние сети соответствующих кодеров.

```text
hermes-coder-velvet -> velvet-db -> velvet-db-proxy -> velvet_backend -> postgres
hermes-coder-max    -> max-db    -> max-db-proxy    -> romaticclub_default -> postgres
```

Для GitHub, Telegram и Byesu оба coder-контейнера используют отдельную egress-сеть.

## Модели

```text
Основная:   gpt-5.4-mini
Усиленная:  gpt-5.6-terra
Резервная:  gpt-5.6-luna
```

Telegram aliases:

```text
/model mini
/model terra
/model luna
```

## Предварительные условия

До установки должны существовать read-only env-файлы:

```text
/srv/hermes-coders/secrets/velvet-db.env
/srv/hermes-coders/secrets/max-db.env
```

Поддерживаются два формата:

```env
DATABASE_URL=postgresql://readonly_user:password@postgres:5432/database
```

или:

```env
PGHOST=postgres
PGPORT=5432
PGDATABASE=database
PGUSER=readonly_user
PGPASSWORD=password
```

Preflight требует:

```text
Velvet: user=hermes_velvet_ro, db=velvet
Max:    user=hermes_max_ro, db=card_hunter
```

## Установка без запуска

После слияния PR и обновления `/srv/velvet`:

```bash
cd /srv/velvet
sudo bash deploy/hermes-coders/install.sh
```

Installer:

1. создаёт `/srv/hermes-coders`;
2. клонирует два отдельных workspace;
3. копирует только модельные ключи из `/srv/velvet/.env.hermes`;
4. не копирует Telegram token и GitHub token оператора;
5. устанавливает model routing, `SOUL.md` и Git credential helper;
6. собирает coder и DB-proxy images;
7. устанавливает, но не запускает `hermes-coders.service`.

## Заполнение отдельных токенов

В файлах ниже должны быть разные Telegram и GitHub токены:

```text
/srv/hermes-coders/secrets/velvet.env
/srv/hermes-coders/secrets/max.env
```

Безопаснее открыть каждый через `sudoedit`:

```bash
sudoedit /srv/hermes-coders/secrets/velvet.env
sudoedit /srv/hermes-coders/secrets/max.env
sudo chmod 600 /srv/hermes-coders/secrets/*.env
sudo chown velvet:velvet /srv/hermes-coders/secrets/*.env
```

Fine-grained GitHub token для Velvet ограничивается репозиторием `Stellmaria/Velvet`, а токен Max только `Stellmaria/romatic_club_bot_max`. Минимально нужны Contents и Pull requests read/write. Не выдавать Administration, Actions secrets и доступ к другим репозиториям.

Один Telegram bot token нельзя использовать в двух gateway одновременно. Preflight специально блокирует такую попытку.

## Preflight и запуск

```bash
sudo -u velvet \
  HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 /srv/velvet/deploy/hermes-coders/preflight.py

sudo systemctl enable --now hermes-coders.service
sudo systemctl --no-pager --full status hermes-coders.service
```

Проверка контейнеров:

```bash
cd /srv/velvet/deploy/hermes-coders
HERMES_CODERS_ROOT=/srv/hermes-coders \
  docker compose --profile velvet --profile max -f compose.yaml ps

HERMES_CODERS_ROOT=/srv/hermes-coders \
  docker compose --profile velvet --profile max -f compose.yaml logs --tail=100
```

## Проверка изоляции

Coder-контейнеры должны видеть только egress и свою внутреннюю DB-сеть:

```bash
docker inspect hermes-coders-hermes-coder-velvet-1 \
  --format '{{json .NetworkSettings.Networks}}'

docker inspect hermes-coders-hermes-coder-max-1 \
  --format '{{json .NetworkSettings.Networks}}'
```

На coder-контейнерах не должно быть сетей `velvet_backend` и `romaticclub_default`.

Проверка read-only identity:

```bash
cd /srv/velvet/deploy/hermes-coders

HERMES_CODERS_ROOT=/srv/hermes-coders \
  docker compose --profile velvet -f compose.yaml exec -T hermes-coder-velvet \
  sh -ceu 'psql "$DATABASE_URL" -Atc "select current_user,current_database(),current_setting('"'"'default_transaction_read_only'"'"');"'

HERMES_CODERS_ROOT=/srv/hermes-coders \
  docker compose --profile max -f compose.yaml exec -T hermes-coder-max \
  sh -ceu 'psql "$DATABASE_URL" -Atc "select current_user,current_database(),current_setting('"'"'default_transaction_read_only'"'"');"'
```

Ожидается `on` и соответствующая роль `hermes_*_ro`.

## Telegram smoke

В каждом отдельном боте:

```text
/new
/model mini
Ответь строго одним словом: OK

/new
/model terra
Ответь строго одним словом: OK

/new
/model luna
Ответь строго одним словом: OK
```

Затем дать безопасную задачу только на чтение:

```text
Покажи текущий репозиторий, ветку и статус Git. Ничего не изменяй.
```

Velvet-coder обязан назвать `Stellmaria/Velvet`, Max-coder обязан назвать `Stellmaria/romatic_club_bot_max`.

## Остановка

```bash
sudo systemctl stop hermes-coders.service
```

Аварийное удаление только контейнеров и сетей, без удаления data/workspaces/secrets:

```bash
cd /srv/velvet/deploy/hermes-coders
HERMES_CODERS_ROOT=/srv/hermes-coders \
  docker compose --profile velvet --profile max -f compose.yaml down
```

Не использовать `down -v`: bind-mounted data, workspaces и secrets должны сохраняться.
