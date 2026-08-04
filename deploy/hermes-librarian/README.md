# Velvet Librarian runtime

Velvet Librarian является отдельным Hermes runtime без Telegram/GitHub credentials, host ports и инструментов. Он доступен только контейнеру Velvet bot через сеть `velvet_backend`.

Текстовый анализ выполняется ботом напрямую через private Ollama `/api/chat` и alias `velvet-librarian-text:v1` (`qwen3:4b-instruct`, контекст 8192). `/storage_ask` сохраняет Hermes Runs API, настроенный на тот же private Ollama. Alias `velvet-librarian-vision:v1` (`qwen3.5:9b-q4_K_M`, контекст 16384) только подготовлен: image support не считается готовой, пока Storage pipeline не передаёт image bytes. Cloud fallback отсутствует.

SOUL и AGENTS собираются из `brain-vault/manifest.json`; installer проверяет
SHA-256 перед запуском. Librarian по-прежнему не получает terminal, file, web,
memory, skills или delegation tools. Он может вернуть schema-bound memory
proposal, но не может записать его: проверку выполняет Каэль, versioned запись —
Velvet Coder через PR.

Установка:

```bash
sudo bash /srv/velvet/deploy/hermes-librarian/install.sh
```

Первый запуск скачивает образ Ollama и обе source models, поэтому systemd допускает до 30 минут. Модели хранятся в существующем Docker volume `velvet_librarian_ollama`; installer его не удаляет.

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
  exec -T ollama-librarian ollama show velvet-librarian-text:v1

sudo docker compose \
  --env-file /srv/velvet/.env.server \
  -f /srv/velvet/deploy/hermes-librarian/compose.yaml \
  exec -T ollama-librarian ollama show velvet-librarian-vision:v1
```

Первый rollout выполняется только с `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`.
