# Дедупликация Hermes incident episode

- Дата: 2026-08-08
- ID: `2026-08-08-hermes-incident-episode-dedupe`
- Линия/фаза: hotfix / supervisor incident reliability
- Статус: `завершено`
- Ветка: `fix/hermes-incident-episode-dedupe`
- Базовый commit: `a392df96e1cd113ff5bbe6e6e22246984d6b50ec`

## Перед началом

### Цель

Остановить повторные Hermes-разборы одного непрерывного outage, не отключая первый полезный incident signal.

### Исходный контекст

Production monitor создавал отдельные incident runs при последовательных состояниях одного сбоя: `container-auto-restarted`, затем `container-unhealthy`, затем `container-not-running`. Существующий cooldown сравнивал полный `event_key`, поэтому смена reason/status обходила дедупликацию и воспринималась как новый инцидент.

### Планируемый объём

- считать непрерывную деградацию одним incident episode;
- открывать episode только после успешного submit в Hermes;
- не разрешать повторный submit при смене degraded state внутри episode;
- закрывать episode только после подтверждённого `running=true` и `health=healthy`;
- сохранять состояние episode в runtime state monitor;
- закрепить поведение регрессионными тестами.

### Критерии готовности

- первый реальный outage по-прежнему эскалируется;
- `auto-restarted -> unhealthy -> not-running` не создаёт новые Hermes runs без healthy recovery между ними;
- `starting` не считается восстановлением;
- после `healthy` новый независимый outage снова может быть эскалирован;
- monitor остаётся read-only относительно Docker runtime.

### Риски и ограничения

Патч не исправляет первопричину падения bot container и не выполняет restart/redeploy. Он меняет только дедупликацию server incident escalation. Если контейнер не достигает `healthy`, один episode намеренно остаётся открытым и повторный Hermes analysis не запускается на каждую смену симптома.

## После завершения

### Фактически сделано

В `HermesIncidentMonitor` добавлено persisted-состояние `incident_episode_open`. После успешного `submit_async` episode открывается. `_can_submit` блокирует последующие события, даже если изменился `event_key`. Episode закрывается только на probe с `running=true` и `health=healthy`.

Существующий cooldown одинаковых event keys сохранён как дополнительная защита после recovery.

### Изменённые модули и контракты

- `scripts/hermes_incident_monitor.py`: episode-level dedupe и persisted recovery state;
- `tests/test_server_hermes_incident_monitor.py`: regression tests для follow-up degraded states и healthy recovery;
- `docs/worklog/2026-08-08-hermes-incident-episode-dedupe.md`: запись hotfix.

### Миграции и совместимость

Миграции БД не требуются. Старые state-файлы совместимы: при отсутствии `incident_episode_open` используется `False`.

### Проверки

PR запускает обязательные GitHub Actions: tests, type check, Docker build, security supply chain, project notes contract и branch protection contract.

### PR и commit

PR: #744 `Fix Hermes incident escalation loop`.

Логика и тесты опубликованы в ветке `fix/hermes-incident-episode-dedupe`.

### Незавершённое

Применение изменения на production требует штатного обновления Velvet до merged `main`; из этой GitHub-сессии host-level service restart/deploy недоступен.

### Следующий шаг

Слить PR после зелёного CI, затем штатно обновить production и подтвердить, что один непрерывный outage создаёт только один Hermes incident run до healthy recovery.
