# Velvet Librarian runtime

Velvet Librarian является отдельным Hermes runtime без Telegram/GitHub credentials, host ports и инструментов. Он доступен только контейнеру Velvet bot через сеть `velvet_backend`.

Установка:

```bash
sudo bash /srv/velvet/deploy/hermes-librarian/install.sh
```

Проверка:

```bash
sudo systemctl status velvet-librarian.service --no-pager --full
sudo docker compose \
  --env-file /srv/velvet/.env.server \
  -f /srv/velvet/deploy/hermes-librarian/compose.yaml \
  ps
```

Первый rollout выполняется только с `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`.
