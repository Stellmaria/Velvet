# Krita на сервере Velvet

## Назначение

Этот режим переносит обработку водяных знаков с Windows-ПК на Linux VPS. Бот и Krita используют один файловый bridge внутри `${VELVET_DATA_DIR}/runtime/krita`. Krita запускается в отдельном контейнере без сети и без Telegram, PostgreSQL или provider-секретов.

## Архитектура

```text
Telegram → Velvet Bot container
                ↓
       /app/runtime/krita
                ↓
   Krita container + Xvfb
                ↓
       preview / final PNG
```

Krita работает как обычное GUI-приложение внутри виртуального X-сервера `Xvfb`. Плагин `velvet_logo` включён заранее через `/home/velvet/.config/kritarc` и каждые 1 секунду проверяет bridge-запросы.

## Первый запуск

После слияния и обновления `/srv/velvet` выполните:

```bash
cd /srv/velvet
sudo bash deploy/server/install-krita-server.sh
```

Установщик:

1. выставляет в `.env.server`:

   ```env
   KRITA_WATERMARK_ENABLED=true
   KRITA_REMOTE_WORKER_ENABLED=false
   KRITA_BRIDGE_DIR=/app/runtime/krita
   ```

2. создаёт bridge-каталоги с владельцем UID/GID `10001`;
3. устанавливает `velvet-krita.service`;
4. перезапускает контейнер бота, чтобы он перечитал env;
5. собирает и запускает контейнер Krita;
6. ждёт Docker healthcheck;
7. прогоняет реальный PNG через плагин и проверяет результат.

## Проверка состояния

```bash
systemctl status velvet-krita.service --no-pager
docker compose --env-file .env.server -f docker-compose.server.yml --profile watermark ps
docker compose --env-file .env.server -f docker-compose.server.yml --profile watermark logs --tail 200 krita
```

Повторный end-to-end smoke:

```bash
cd /srv/velvet
sudo -u velvet bash deploy/server/krita-smoke.sh .env.server
```

Smoke создаёт временный PNG и настоящий request schema v2, ждёт response от плагина и проверяет PNG-сигнатуру output. Успешные временные файлы удаляются. При ошибке они остаются в `${VELVET_DATA_DIR}/runtime/krita` для диагностики.

## Обычный деплой

`deploy/server/deploy.sh` автоматически выбирает режим:

- `KRITA_WATERMARK_ENABLED=true` и `KRITA_REMOTE_WORKER_ENABLED=false`: собирает и поднимает серверную Krita, затем выполняет smoke;
- `KRITA_REMOTE_WORKER_ENABLED=true`: локальная Krita останавливается, используется удалённый worker;
- `KRITA_WATERMARK_ENABLED=false`: локальная Krita останавливается.

## Ограничения ресурсов

Значения можно задать в `.env.server`:

```env
KRITA_SERVER_IMAGE=velvet-krita-server:local
KRITA_SERVER_MEMORY_LIMIT=3g
KRITA_SERVER_CPU_LIMIT=1.5
KRITA_XVFB_SCREEN=1920x1080x24
```

Krita использует программный OpenGL. Контейнер имеет `network_mode: none`, сброшенные Linux capabilities и `no-new-privileges`.

## Остановка и откат

Отключить серверную Krita без удаления данных:

```bash
sudo systemctl disable --now velvet-krita.service
```

Затем измените `.env.server`:

```env
KRITA_WATERMARK_ENABLED=false
```

и перезапустите бот:

```bash
sudo systemctl reload-or-restart velvet-compose.service
```

Для возврата к Windows-worker включите `KRITA_REMOTE_WORKER_ENABLED=true` и используйте процедуру из `.env.krita-remote.example`. Одновременно серверный и удалённый worker включать нельзя.

## Обновление образа вручную

```bash
cd /srv/velvet
docker compose --env-file .env.server -f docker-compose.server.yml --profile watermark build --pull krita
sudo systemctl reload velvet-krita.service
```
