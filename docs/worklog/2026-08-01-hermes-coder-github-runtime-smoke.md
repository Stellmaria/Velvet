# Сессия: проверяемый GitHub-доступ Hermes Coder

- Дата: 2026-08-01
- ID: `hermes-coder-github-runtime-smoke-20260801`
- Линия/фаза: Hermes coder orchestration / runtime reliability
- Статус: `частично`
- Ветка: `fix/hermes-coder-github-runtime-smoke`
- Базовый commit: `e6715aa3f77bbe99da2d3e63387a54189d563dbd`

## Перед началом

### Цель

Сделать GitHub-доступ Velvet Coder и Max Coder проверяемым на фактически запущенном runtime, чтобы coder-агент не мог считаться готовым, если он не способен самостоятельно выполнить push и создать pull request в своём репозитории.

Дополнительно сохранить private Runs API credentials при повторной установке coder-инфраструктуры.

### Исходный контекст

Max Coder подготовил локальную ветку с исправлением, но не смог выполнить `push` и создать pull request. Статический preflight считался успешным, потому что проверял наличие `GH_TOKEN` в secret env и `terminal.env_passthrough` в runtime YAML, но не проверял GitHub credential внутри уже запущенного container runtime.

Публикацию пришлось повторить через внешний GitHub-коннектор. Это аварийный обход, а не штатный маршрут оркестрации.

Контур имел две независимые слабости:

1. systemd завершал запуск после `docker compose up -d`, не подтверждая живую GitHub-аутентификацию, origin и write-доступ обоих coder-контейнеров;
2. повторный запуск `deploy/hermes-coders/install.sh` переписывал coder env без сохранения существующего `API_SERVER_KEY`, поэтому переустановка могла восстановить GitHub-настройку и одновременно сломать private Runs API.

Главный Каэль намеренно не получает GitHub-токен Max. Раздельные repo-scoped credentials остаются обязательной границей.

### Планируемый объём

- добавить post-start smoke для обоих Hermes Coder gateway;
- проверить живой `GH_TOKEN`, runtime passthrough, GitHub identity, repository origin и credential helper;
- подтвердить фактическое write-разрешение без создания ветки;
- сделать systemd запуск fail-closed при нерабочем GitHub-доступе;
- очищать диагностический вывод от token-like значений;
- сохранить `API_SERVER_KEY` при повторном запуске installer;
- добавить unit, contract tests и production rollout instructions.

### Критерии готовности

- Velvet Coder подтверждает auth и push только для `Stellmaria/Velvet`;
- Max Coder подтверждает auth и push только для `Stellmaria/romatic_club_bot_max`;
- проверка не создаёт ветки, PR или иные GitHub mutations;
- `hermes-coders.service` не объявляет успешный старт при сломанном token, passthrough, origin или credential helper;
- повторная установка не удаляет существующий `API_SERVER_KEY`;
- focused tests, type check, project notes contract, tests workflow и Docker workflow проходят;
- production journal содержит `AUTH_OK, PUSH_OK` для обоих проектов.

### Риски и ограничения

`git push --dry-run` требует доступности GitHub во время старта unit. При внешнем outage сервис будет отмечен как failed, хотя уже созданные контейнеры могут продолжать работать. Это намеренный fail-closed контракт: coder без подтверждённой возможности публикации не считается готовым.

Smoke не создаёт реальную ветку и не проверяет полный `gh pr create`; право на push и Pull requests write дополнительно подтверждается первой небольшой реальной coder-задачей после rollout. Токены остаются раздельными и не передаются Каэлю.

## После завершения

### Фактически сделано

- добавлен `deploy/hermes-coders/runtime_smoke.py`;
- smoke ждёт health обоих gateway;
- для каждого живого контейнера проверяются `GH_TOKEN`, `terminal.env_passthrough`, `gh api user`, ожидаемый repository, HTTPS origin и `gh auth git-credential`;
- фактическое write-разрешение проверяется через `git push --dry-run` в временное имя ref без создания ветки;
- диагностический вывод очищается от GitHub token-like значений;
- `hermes-coders.service` запускает smoke после `start` и после `reload`;
- `deploy/hermes-coders/install.sh` сохраняет существующий `API_SERVER_KEY`, требует smoke-скрипт и показывает ручную команду проверки;
- добавлены unit и contract tests ожидания gateway, dry-run push, redaction, systemd order и сохранения Runs API key;
- открыт PR #539.

### Миграции и совместимость

SQL-миграций нет. Production базы данных, Docker networks и API routes не меняются. Существующие repo-scoped `GH_TOKEN`, Telegram credentials, read-only DB identities и coder workspaces сохраняются.

Изменение installer обратно совместимо: существующий `API_SERVER_KEY` теперь сохраняется вместо удаления. Если ключ отсутствовал, preflight по-прежнему блокирует запуск до его безопасной генерации orchestration installer.

### Проверки

До открытия PR локально прошли:

- `python -m py_compile deploy/hermes-coders/runtime_smoke.py`;
- `bash -n deploy/hermes-coders/install.sh`;
- 5 focused unit/contract tests.

На текущем PR уже прошёл type check. Полные tests, Docker build и повторный project notes contract выполняются GitHub Actions после обновления этой записи.

### PR и commit

- PR: `https://github.com/Stellmaria/Velvet/pull/539`;
- ветка: `fix/hermes-coder-github-runtime-smoke`;
- текущий head до финального CI: будет определён после коммита этой записи;
- merge commit: ожидается после зелёного CI и явного разрешения владельца.

### Незавершённое

- дождаться полного зелёного CI PR #539;
- слить PR после явного разрешения владельца;
- обновить `/srv/velvet` и переустановить `hermes-coders.service`;
- получить production `AUTH_OK, PUSH_OK` для обоих coder runtime;
- выполнить небольшую реальную задачу Max Coder с самостоятельными branch, push и pull request.

### Следующий шаг

После зелёного CI и merge обновить VPS, выполнить `deploy/hermes-coders/install.sh`, перезапустить `hermes-coders.service`, проверить journal и затем дать Max Coder безопасную небольшую задачу для end-to-end подтверждения публикации без внешнего GitHub-коннектора.
