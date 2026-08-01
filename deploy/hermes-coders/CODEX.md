# Codex GPT-5.6 для Hermes coder

Этот слой переводит задания главного Hermes с Byesu-backed coder gateway на локальный OpenAI Codex CLI, авторизованный через ChatGPT-план владельца.

## Архитектура

```text
@VelvetHermesBot
  -> hermes-coder-router
    -> hermes-coder-velvet  (Codex CLI, Stellmaria/Velvet)
    -> hermes-coder-max     (Codex CLI, Stellmaria/romatic_club_bot_max)

@velvet_private_coder_bot -> hermes-chat-velvet (старый Hermes/Byesu chat)
@romatic_max_coder_bot    -> hermes-chat-max    (старый Hermes/Byesu chat)
```

Codex runners не получают production Docker socket, systemd, production checkout или прямой доступ к production PostgreSQL networks. Каждый проект имеет отдельные:

- Git workspace;
- `CODEX_HOME` и `auth.json`;
- Runs API key;
- run journal;
- GitHub token;
- контейнер и resource limits.

## Модели и маршрутизация

```text
Мелкая правка, README, документация, переименование -> gpt-5.6-luna
Обычная разработка и исправление багов              -> gpt-5.6-terra
Архитектура, миграции, security, большой рефактор   -> gpt-5.6-sol
```

Явный выбор в тексте задачи имеет приоритет:

```text
/model luna
/model terra
/model sol
```

Также поддерживаются формы `модель: луна`, `модель: терра` и `модель: сол`.

При model/rate/capacity error действует резервная цепочка:

```text
Terra -> Sol -> Luna
Luna  -> Terra -> Sol
Sol   -> Terra -> Luna
```

Разрешены только:

```text
gpt-5.6-luna
gpt-5.6-terra
gpt-5.6-sol
```

Codex CLI закреплён на `0.144.4`. Образ скачивает официальный release asset и проверяет опубликованный SHA-256 digest до установки.

## Подготовка на VPS

После обновления `/srv/velvet` на commit с этим изменением:

```bash
cd /srv/velvet
sudo bash deploy/hermes-coders/install-codex.sh
```

Installer:

1. создаёт `/srv/hermes-coders/codex/{velvet,max}`;
2. создаёт отдельные `/srv/hermes-coders/workspaces/{velvet-codex,max-codex}`;
3. создаёт отдельные журналы `/srv/hermes-coders/codex-runs/{velvet,max}`;
4. добавляет разные `CODEX_RUNNER_API_KEY` без вывода значений;
5. записывает безопасный `config.toml`;
6. собирает Codex runner images;
7. не запускает runners до интерактивной авторизации.

## Авторизация

Каждый профиль нужно авторизовать отдельно:

```bash
sudo bash deploy/hermes-coders/codex-login.sh velvet
sudo bash deploy/hermes-coders/codex-login.sh max
```

Команда использует:

```text
codex login --device-auth
```

Codex покажет URL и одноразовый код. Откройте URL в браузере, войдите в ChatGPT и подтвердите код. Значение `auth.json` нельзя печатать, копировать в репозиторий или передавать между проектами.

После входа должны существовать:

```text
/srv/hermes-coders/codex/velvet/auth.json
/srv/hermes-coders/codex/max/auth.json
```

Оба файла должны иметь режим `0600`.

## Проверка и запуск

```bash
sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 deploy/hermes-coders/preflight.py

sudo systemctl restart hermes-coders.service
sudo systemctl restart hermes-coder-router.service

sudo env HERMES_CODERS_ROOT=/srv/hermes-coders \
  python3 deploy/hermes-coders/runtime_smoke.py
```

Ожидаемый итог smoke:

```text
CHAT_OK, CODEX_AUTH_OK, LUNA_TERRA_SOL_OK, PUSH_OK
```

## Поведение Runs API

Runner сохраняет совместимость с существующим router:

```text
GET  /health
GET  /v1/capabilities
POST /v1/runs
GET  /v1/runs/{run_id}
POST /v1/runs/{run_id}/stop
```

Одновременно выполняется только одна задача на проект. Остальные runs ждут в очереди внутри процесса. Статус и очищенный вывод сохраняются атомарно в JSON-файлах с режимом `0600`.

## Безопасность окружения

Codex работает в `workspace-write`; GitHub network включён внутри изолированного coder-контейнера. Apps, plugins и tool suggestions выключены.

Codex shell не получает:

- `API_SERVER_KEY`;
- Byesu model keys;
- `CODEX_RUNNER_API_KEY`;
- database URL/password;
- Telegram bot token.

`GH_TOKEN` намеренно доступен Codex shell, поскольку coder должен создать ветку, push и pull request. Fine-grained token по-прежнему должен быть ограничен одним репозиторием.

## Откат

Остановка Codex backend без удаления данных:

```bash
cd /srv/velvet/deploy/hermes-coders
HERMES_CODERS_ROOT=/srv/hermes-coders \
  docker compose --profile velvet --profile max -f compose.yaml stop \
  hermes-coder-velvet hermes-coder-max
```

Не удалять каталоги `codex`, `codex-runs` и `workspaces/*-codex`, пока не подтверждён полный отказ от этой схемы.
