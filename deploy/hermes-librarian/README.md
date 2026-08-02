# Velvet Librarian runtime

Velvet Librarian является отдельным Hermes runtime без Telegram/GitHub credentials, host ports и инструментов. Он доступен только контейнеру Velvet bot через сеть `velvet_backend`.

Inference выполняется локально сервисом `ollama-librarian` на модели `qwen3.5:9b-q4_K_M`. Installer создаёт локальный alias `velvet-librarian-local:v1` с контекстом 65 536 токенов. Cloud fallback намеренно отсутствует: недоступность локальной модели должна дать явную ошибку, а не скрытый расход провайдерских токенов.

SOUL и AGENTS собираются из `brain-vault/manifest.json`; installer проверяет
SHA-256 перед запуском. Librarian по-прежнему не получает terminal, file, web,
memory, skills или delegation tools. Он может вернуть schema-bound memory
proposal, но не может записать его: проверку выполняет Каэль, versioned запись —
Velvet Coder через PR.

Установка:

```bash
sudo bash /srv/velvet/deploy/hermes-librarian/install.sh
```

Первый запуск скачивает образ Ollama и модель около 6,6 ГБ, поэтому systemd допускает до 30 минут. Модель хранится в отдельном Docker volume `velvet_librarian_ollama`.

Проверка:

```bash
sudo systemctl status velvet-librarian.service --no-pager --full
sudo docker compose \
  --env-file /srv/velvet/.env.server \
  -f /srv/velvet/deploy/hermes-librarian/compose.yaml \
  ps

sudo docker compose \
  --env-file /srv/velvet/.env.server \
  -f /srv/velvet/deploy/hermes-librarian/compose.yaml \
  exec -T ollama-librarian ollama show velvet-librarian-local:v1
```

Первый rollout выполняется только с `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`.
