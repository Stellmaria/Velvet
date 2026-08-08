# Сохранение optional profile services при server deploy

- Дата: 2026-08-08
- ID: #630
- Линия/фаза: Server lifecycle / production repair
- Статус: завершено
- Ветка: `fix/preserve-profile-services-on-deploy`
- Базовый commit: `f0223d62a5b9039fa92c7d50929418d92fdf2f43`

## Перед началом

### Цель

Убрать destructive orphan cleanup из обычного server deploy/startup, чтобы
частичный запуск core-сервисов не мог удалить уже работающие profile-gated
контейнеры, включая локальный Vision runtime.

### Исходный контекст

Production-диагностика 2026-08-08 обнаружила `vision-gateway` в состоянии
`unhealthy` при полном отсутствии контейнера `vision-runtime`. Gateway стабильно
возвращал HTTP 503, потому что hostname `vision-runtime` больше не разрешался во
внутренней Docker-сети.

Модель при этом не была потеряна: `${VELVET_DATA_DIR}/vision` сохранил
`qwen3.5:9b` с digest `6488c96fa5fa`. Пересборка runtime image и штатный запуск
профиля `vision` восстановили оба сервиса в `healthy` без повторного скачивания
модели.

Обычный deployment path и systemd lifecycle использовали `docker compose up
--remove-orphans`, выбирая только core services. При наличии optional Compose
profiles orphan cleanup не должен быть побочным эффектом частичного запуска.

### Планируемый объём

- удалить `--remove-orphans` из `start_core_services()` server deploy;
- удалить `--remove-orphans` из systemd `ExecStart` и `ExecReload`;
- оставить явное orphan cleanup отдельной maintenance-операцией;
- добавить regression contracts для обоих lifecycle paths;
- сохранить остальные deployment, rollback и health semantics без изменений.

### Критерии готовности

- core deploy запускает только требуемые сервисы и не запрашивает orphan prune;
- systemd start/reload не запрашивает orphan prune;
- существующие profile-gated containers не становятся объектом cleanup из-за
  обычного core lifecycle;
- shell/deployment contracts и обязательный CI остаются зелёными.

## После завершения

### Фактически сделано

- `deploy/server/deploy.sh`: `start_core_services()` больше не передаёт
  `--remove-orphans`;
- `deploy/systemd/velvet-compose.service`: флаг удалён из `ExecStart` и
  `ExecReload`;
- существующий deployment contract обновлён под безопасную core-команду;
- добавлен отдельный regression test, запрещающий возврат orphan prune в
  обычные deploy/systemd lifecycle paths.

### Production evidence

После ручного восстановления:

- `velvet-vision-runtime-1`: `healthy`, restart count 0, OOM false;
- `velvet-vision-gateway-1`: `healthy`;
- model: `qwen3.5:9b`;
- pinned digest: `6488c96fa5fa`;
- `vision-model-loader` подтвердил `Vision model already installed`;
- model volume был переиспользован без повторной загрузки 6.6 GB модели.

Этот срез устраняет destructive risk из обычного lifecycle. Он не утверждает,
что конкретный исторический запуск `--remove-orphans` доказан как единственная
команда, удалившая production runtime.

### Проверки

PR запускает обязательные repository checks, включая deployment/unit contracts,
type check, Docker build, security/supply-chain gates и project notes contract.

### PR

- PR: #723.
