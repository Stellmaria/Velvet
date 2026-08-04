# Сессия: AppArmor Git HTTPS lifecycle Hermes coders

- Дата: `2026-08-05`
- ID: `hermes-apparmor-git-https-lifecycle-20260805`
- Линия/фаза: `server operations / Hermes coder systemd reconciliation`
- Статус: `частично`
- Ветка: `fix/hermes-apparmor-git-https-lifecycle`
- Базовый commit: `cc22b85068127327cda87ca7315a5470d0e76b9c`
- Связанные issue, PR и release evidence: `#592`, `#626`, release run `30956213247`

## Перед началом

### Цель

Исправить подтверждённое production-падение one-time systemd reconciler без
ослабления sandbox и без расширения blast radius на Hermes chat gateways и DB
proxies.

### Исходный контекст

Exact release `f875062956c707b81e3a2e3b095c0c80c5cd442a` успешно выпущен. Оба
coder-контейнера были `running`, `healthy`, restart count `0`, `init=true`.
Первый запуск `reconcile_release_systemd.sh` прошёл source guard, runtime config,
workspace reconcile, preflight и Compose startup, но `runtime_smoke.py` упал при
HTTPS clone:

```text
fatal: cannot exec 'remote-https': Permission denied
```

Production journal также показал, что blanket `docker compose up` пересоздал
`hermes-chat-velvet`, `hermes-chat-max` и затронул DB proxies, хотя systemd unit
должен управлять только двумя coder services. Transactional rollback восстановил
предыдущие units, legacy override и два здоровых coder-контейнера.

### Планируемый объём

- разрешить AppArmor execution для Git HTTP/HTTPS transport helpers;
- включить установку host AppArmor profile в release reconciler;
- резервировать и восстанавливать прежний профиль при rollback;
- fail closed, если approved release profile не содержит helper rules;
- ограничить systemd start/reload/stop сервисами `hermes-coder-velvet` и
  `hermes-coder-max`;
- использовать `--no-deps --no-build` для start/reload;
- добавить regression contracts по фактическому production failure;
- открыть PR и слить только после зелёного required CI;
- не выполнять production release или повторный reconciler в рамках PR.

### Критерии готовности

- AppArmor profile содержит `ix` для `git-remote-http` и `git-remote-https`;
- reconciler устанавливает profile до systemd start;
- rollback возвращает прежний host profile до восстановления контейнеров;
- coder unit не запускает и не останавливает chat/proxy services;
- Bash sources парсятся, contract tests проходят;
- все required branch-protection contexts зелёные;
- merge выполняется штатно, без обхода protection.

### Риски и ограничения

- путь Git helpers фиксирован для текущего Ubuntu/Debian image layout:
  `/usr/lib/git-core`;
- profile reload требует root и включённый AppArmor;
- production rollout остаётся отдельной операцией после нового exact-main
  release;
- текущие healthy coder-контейнеры нельзя перезапускать до выпуска исправления;
- rollback backup от первой попытки reconciliation сохраняется.

## После завершения

### Фактически сделано

- в AppArmor profile добавлены execution rules для Git HTTP/HTTPS helpers;
- systemd coder lifecycle ограничен двумя coder services;
- start/reload используют `--no-deps --no-build`;
- stop получает явные coder service targets;
- reconciler проверяет AppArmor availability и наличие helper rules;
- current host profile резервируется вместе с units и legacy overrides;
- approved release profile устанавливается и reload-ится до systemd start;
- rollback сначала восстанавливает прежний AppArmor profile, затем прежние
  coder-контейнеры и units;
- добавлен отдельный regression contract test module.

### Риски и ограничения

- реальный production retry выполняется только после merge и нового exact-main
  release;
- до retry systemd может оставаться `failed/inactive`, при этом coder runtime
  продолжает работать в здоровых контейнерах;
- изменение не ослабляет mount, userns, read-only workspace или network policy.

### Миграции и совместимость

- database migrations отсутствуют;
- persistent data, auth, runs, workspaces, secrets и volumes не меняются;
- Docker images не rebuild-ятся systemd lifecycle;
- chat gateways и DB proxies исключены из coder unit mutation surface;
- старый AppArmor profile и legacy Compose override сохраняются в rollback backup.

### Проверки

Добавлены contract tests для:

- executable Git HTTPS helpers в AppArmor profile;
- coder-only systemd service targets;
- `--no-deps --no-build` start/reload contract;
- transactional AppArmor install и rollback;
- fail-closed rejection профиля без helper rules.

### PR и commit

- ветка: `fix/hermes-apparmor-git-https-lifecycle`;
- base: `cc22b85068127327cda87ca7315a5470d0e76b9c`;
- PR и merge commit фиксируются после публикации и required CI.

### Незавершённое

- открыть PR;
- дождаться required CI и исправить только подтверждённые failures;
- синхронизировать с `main`, если он продвинется;
- слить после зелёного CI;
- отдельно выпустить exact-current-main release;
- повторить systemd reconciler и подтвердить `active/exited/0`.

### Следующий шаг

Открыть PR, дождаться всех required branch-protection contexts и выполнить
штатный merge без production действий.
