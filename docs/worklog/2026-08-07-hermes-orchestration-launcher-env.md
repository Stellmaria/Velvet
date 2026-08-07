# Сессия: Hermes orchestration launcher env boundary

- Дата: `2026-08-07`
- ID: `2026-08-07-hermes-orchestration-launcher-env`
- Линия/фаза: Hermes / production orchestration / post-activation validation
- Статус: `частично`
- Ветка: `fix/hermes-orchestration-launcher-env`
- Базовый commit: `5926dec277294a4f2cd69191f9b6dd6050613747`

## Перед началом

### Цель

Устранить production regression в хвосте `deploy/hermes-orchestration/install.sh`, где повторная three-layer Compose validation выполнялась без canonical `launcher.env` и поэтому не видела обязательный `HERMES_SANDBOX_GID`.

### Исходный контекст

Production уже успешно активировал canonical coder infrastructure после AppArmor hotfix: `hermes-coders.service` и `hermes-coder-router.service` active, оба coder containers healthy, `coderctl.py health all` подтверждает authenticated Velvet/Max, а основной bot резолвит `hermes-coder-router`.

После этого orchestration installer продолжил post-activation шаги и упал на собственной дополнительной команде `docker compose ... config --quiet` с сообщением `HERMES_SANDBOX_GID is missing a value`. Canonical coder installer до этого уже создал `/srv/hermes-coders/launcher.env`; systemd unit использует тот же файл как `EnvironmentFile`, поэтому runtime был healthy, а ошибка относилась только к orchestration tail.

### Планируемый объём

- не вычислять и не дублировать sandbox GID в orchestration;
- переиспользовать canonical `$CODERS_ROOT/launcher.env` для обеих three-layer Compose команд orchestration;
- fail-closed проверять, что launcher env существует и не является symlink;
- не менять coder runtime, provider routing, secrets, AppArmor или network boundary;
- добавить regression coverage.

### Критерии готовности

- orchestration Compose `config` получает `HERMES_SANDBOX_GID` из canonical launcher env;
- финальный orchestration Compose `ps` использует тот же env source;
- orchestration не содержит собственной записи `HERMES_SANDBOX_GID=`;
- existing runtime health contract не меняется;
- protected CI зелёный на exact PR head.

### Риски и ограничения

Изменение не исправляет и не маскирует failures внутри canonical coder installer. Если `launcher.env` не создан или небезопасен, orchestration должен завершиться fail-closed до дополнительной Compose validation.

## После завершения

### Фактически сделано

`deploy/hermes-orchestration/install.sh` теперь определяет `CODERS_LAUNCHER_ENV="$CODERS_ROOT/launcher.env"`, после canonical coder installer проверяет его как обычный файл без symlink и передаёт через `docker compose --env-file` как в post-install `config --quiet`, так и в финальный `ps`.

Значение `HERMES_SANDBOX_GID` по-прежнему создаётся и принадлежит canonical coder/launcher lifecycle. Orchestration его не вычисляет и не сохраняет самостоятельно.

`tests/test_hermes_orchestration_installer_mode.py` фиксирует exact launcher-env reuse и запрещает локальную запись `HERMES_SANDBOX_GID=` в orchestration installer.

### Миграции и совместимость

SQL, application env schema и secret values не меняются. Existing `/srv/hermes-coders/launcher.env` остаётся canonical runtime artifact. Изменение только устраняет рассинхронизацию между systemd/coder installer и дополнительными orchestration Compose командами.

### Проверки

Protected CI требуется на финальном PR head. Production повторный orchestration reconcile выполняется только после merge terminal-green head. До этого текущие healthy coders/router не перезапускаются этим hotfix.

### Следующий шаг

- открыть PR;
- дождаться terminal green required checks;
- подтвердить `behind_by=0`;
- merge exact head;
- штатно обновить production;
- повторить orchestration installer и получить его terminal success;
- после этого отдельно включить `CODEX_IMAGE_BYESU_FALLBACK_ENABLED=true`, перезапустить canonical coder service и подтвердить split-key image provider smoke перед live GPT Image 2 тестами.
