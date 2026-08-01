# Hermes Coder GitHub runtime smoke

## Контекст

Max Coder подготовил локальную ветку с исправлением, но не смог выполнить `push` и создать pull request. Статический preflight считался успешным, потому что проверял наличие `GH_TOKEN` в secret env и `terminal.env_passthrough` в runtime YAML, но не проверял GitHub credential внутри уже запущенного container runtime.

Публикацию пришлось повторить через внешний GitHub-коннектор. Это аварийный обход, а не штатный маршрут оркестрации.

## Корневая причина

Контур имел две независимые слабости:

1. systemd завершал запуск после `docker compose up -d`, не подтверждая живую GitHub-аутентификацию, origin и write-доступ обоих coder-контейнеров;
2. повторный запуск `deploy/hermes-coders/install.sh` переписывал coder env без сохранения существующего `API_SERVER_KEY`, поэтому переустановка могла восстановить GitHub-настройку и одновременно сломать private Runs API.

Главный Каэль намеренно не получает GitHub-токен Max. Раздельные repo-scoped credentials остаются обязательной границей.

## Реализация

Добавлен `deploy/hermes-coders/runtime_smoke.py`. После готовности gateway он проверяет для Velvet Coder и Max Coder:

- наличие `GH_TOKEN` в живом контейнере;
- наличие `GH_TOKEN` в `terminal.env_passthrough` фактического runtime config;
- успешный authenticated вызов `gh api user`;
- правильный repository и HTTPS origin;
- установленный `gh auth git-credential` helper;
- реальное право записи через `git push --dry-run` в временное имя ref.

`--dry-run` заставляет GitHub проверить credential и write scope, но не создаёт ветку и не меняет репозиторий.

`hermes-coders.service` запускает smoke после `start` и `reload`. Ошибка делает запуск unit неуспешным вместо ложного healthy-состояния. Диагностический вывод очищается от token-like значений.

Installer теперь сохраняет существующий `API_SERVER_KEY`, требует smoke-скрипт и показывает ручную команду проверки.

## Проверки

- `python -m py_compile deploy/hermes-coders/runtime_smoke.py`;
- `bash -n deploy/hermes-coders/install.sh`;
- unit/contract tests ожидания gateway, dry-run push, redaction, systemd order и сохранения Runs API key.

## Production rollout

После merge:

```bash
cd /srv/velvet
git pull --ff-only origin main
sudo bash deploy/hermes-coders/install.sh
sudo systemctl restart hermes-coders.service
sudo systemctl --no-pager --full status hermes-coders.service
sudo journalctl -u hermes-coders.service -n 100 --no-pager
```

Для обоих проектов ожидаются строки `AUTH_OK, PUSH_OK`. Затем Max Coder должен выполнить одну небольшую реальную задачу с отдельной веткой и pull request без помощи внешнего GitHub-коннектора.
