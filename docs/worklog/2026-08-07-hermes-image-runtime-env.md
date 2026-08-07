# Сессия: Hermes GPT Image 2 production runtime env wiring

- Дата: 2026-08-07
- ID: `2026-08-07-hermes-image-runtime-env`
- Линия/фаза: Hermes / GPT Image 2 / production hardening
- Статус: частично
- Ветка: `hotfix/image-runtime-config`
- Базовый commit: `981dba2bb36c80d06dd51a073a2632056a57cf6c`
- PR: #669

## Перед началом

### Цель

Исправить production wiring несекретных GPT Image 2 runtime-настроек так, чтобы канонический `hermes-coders.service` передавал их в Docker Compose без загрузки полного operator env и без расширения secret surface coder runtime.

### Исходный контекст

После штатной установки Hermes release `981dba2bb36c80d06dd51a073a2632056a57cf6c` новые GPT Image 2 модули были загружены в healthy coder-контейнеры и основной runtime smoke прошёл. Live runtime при этом показал `CODEX_IMAGE_BYESU_FALLBACK_ENABLED=false`, хотя parameter routing и limit preflight присутствовали в release.

Диагностика установила, что `compose.runtime.yaml` читает image runtime settings из окружения Docker Compose, тогда как systemd lifecycle получает только `/srv/hermes-coders/launcher.env`. Канонический launcher installer намеренно пересоздаёт этот файл только из sandbox/immutable-image параметров, а `.env.hermes` не подключается к systemd целиком. Поэтому image settings из operator env до Compose не доходили.

Отдельно production provider capability probe подтвердил, что текущий shared Byesu credential не видит `gpt-5.6-luna`, `gpt-image-2` и `firefly-gpt-image-2`. Этот внешний credential blocker данным PR не обходится и provider smoke не ослабляется.

### Планируемый объём

- добавить узкий wrapper для запуска Docker Compose с allowlist GPT Image 2 runtime settings из `.env.hermes`;
- не проецировать `BYESU_HERMES_CODEX_API_KEY`, `OPENAI_API_KEY` и любые другие секреты;
- валидировать boolean, timeout и HTTPS base URL fail-closed;
- использовать wrapper для systemd Compose `config`, `up`, `stop` и `reload` lifecycle;
- сохранить immutable launcher/image pinning без изменения;
- добавить regression tests на projection boundary и обновить существующий systemd contract test;
- не менять provider capability smoke и не включать платный image route автоматически.

### Критерии готовности

- в Compose передаются только пять разрешённых image runtime settings;
- существующее окружение systemd/launcher сохраняется;
- operator secrets не добавляются wrapper-ом;
- некорректные image runtime values приводят к fail-closed ошибке;
- systemd не запускает Compose в обход wrapper-а;
- все protected CI checks PR проходят;
- merge PR не считается production activation и не скрывает внешний media-credential blocker.

### Риски и ограничения

- подключение полного `.env.hermes` к systemd недопустимо, потому что расширит secret surface coder runtime;
- wrapper должен сохранять уже установленное launcher/systemd environment и добавлять только allowlist несекретных image settings;
- неправильный boolean, timeout или Byesu URL должен блокировать activation, а не тихо откатываться к неожиданному значению;
- даже после исправления wiring production image route останется заблокированным до установки media-capable Byesu credential;
- provider capability smoke намеренно остаётся fail-closed и не должен ослабляться ради зелёного systemd status.

## После завершения

### Фактически сделано

Добавлен `deploy/hermes-coders/compose_image_runtime_env.py`. Wrapper читает `/srv/velvet/.env.hermes` или явный `HERMES_OPERATOR_ENV`, извлекает только allowlist:

- `CODEX_IMAGE_BYESU_FALLBACK_ENABLED`;
- `CODEX_IMAGE_LIMIT_PREFLIGHT_ENABLED`;
- `CODEX_IMAGE_LIMIT_PREFLIGHT_TIMEOUT_SECONDS`;
- `CODEX_IMAGE_BYESU_BASE_URL`;
- `CODEX_IMAGE_BYESU_TIMEOUT_SECONDS`.

Boolean values нормализуются к `true`/`false`; timeout values проверяются в тех же ограниченных диапазонах, которые принимает runtime; Byesu base URL обязан быть HTTPS без embedded credentials, query или fragment. Symlinked operator env отклоняется.

`deploy/systemd/hermes-coders.service` теперь запускает Docker Compose lifecycle через этот wrapper для `config --quiet`, `up`, `stop` и reload activation. Остальные preflight, runtime smoke и tier provider smoke сохранены без ослабления.

Добавлен `tests/test_hermes_image_runtime_env.py` с проверками allowlist projection, исключения секретов, defaults, invalid-value fail-closed behavior, symlink rejection и systemd lifecycle wiring. Существующий `tests/test_hermes_coders_contract.py` обновлён под канонический wrapper path и продолжает проверять порядок preflight → activation → smoke.

### Миграции и совместимость

SQL-миграций нет. Полный `.env.hermes` не подключается как systemd `EnvironmentFile`. Wrapper наследует уже разрешённое systemd/launcher environment и добавляет только пять несекретных image runtime параметров. Это сохраняет текущие sandbox GID, network и immutable image pins и не расширяет набор operator credentials, доступных Compose lifecycle через новый код.

PR не меняет значение production image opt-in и не подменяет Byesu credential. `CODEX_IMAGE_BYESU_FALLBACK_ENABLED` остаётся выключенным, пока оператор явно не задаст его в production config. Provider capability smoke остаётся fail-closed.

### Проверки

Первый CI прогон обнаружил устаревшее буквальное ожидание direct `/usr/bin/docker compose` в `test_hermes_coders_contract`; runtime-код при этом не падал. Contract test обновлён для нового wrapper path.

Следующий прогон подтвердил прохождение новых image runtime env tests и остальных Hermes контрактов, но project notes contract потребовал отдельную worklog запись. Первый вариант worklog затем выявил обязательные структурные поля самого notes contract; запись приведена к каноническому шаблону без изменения runtime-кода.

### PR и commit

- PR: #669 `Fix Hermes image runtime env wiring`.
- Ветка: `hotfix/image-runtime-config`.
- Базовый commit: `981dba2bb36c80d06dd51a073a2632056a57cf6c`.
- Финальный head и merge commit фиксируются GitHub после полностью зелёного CI; production activation этим PR отдельно не выполняется.

### Незавершённое

- дождаться повторного полностью зелёного CI после исправления worklog;
- merge PR #669 только при неизменном head и mergeable=true;
- на production fast-forward checkout к merge commit;
- заменить shared Byesu credential на media-capable token group, которая видит выбранные GPT-5.6 модели и обе image-модели, не публикуя значение;
- явно включить `CODEX_IMAGE_BYESU_FALLBACK_ENABLED=true` только после успешной capability проверки;
- штатно переустановить/reconcile Hermes и подтвердить systemd success;
- затем выполнить контролируемые live image smoke маршрутов.

### Следующий шаг

После зелёного CI объединить #669 в `main`. Production activation выполнять отдельно после подготовки media-capable Byesu credential; merge этого hotfix сам по себе не является подтверждением работающего платного image route.
