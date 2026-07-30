# Docker host hardening

Перед первым production-запуском объедините параметры из `docker-daemon.json.example` с существующим `/etc/docker/daemon.json`. Не перезаписывайте существующий файл вслепую.

Минимальные параметры Velvet:

- `json-file` log driver;
- `max-size: 20m`;
- `max-file: 5`;
- `live-restore: true`.

После изменения:

```bash
sudo dockerd --validate --config-file /etc/docker/daemon.json
sudo systemctl restart docker
sudo docker info --format '{{json .LoggingDriver}}'
```

`live-restore` помогает работающим контейнерам пережить restart Docker daemon, но не заменяет systemd, Compose restart policy, PostgreSQL dump и внешний uptime-monitor.
