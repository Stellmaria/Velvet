# Сессия: verified-image production bootstrap

- Дата: `2026-08-07`
- ID: `server-bootstrap-verified-deploy-20260807`
- Линия/фаза: `Velvet / production deploy / bootstrap hotfix`
- Статус: `частично`
- Ветка: `hotfix/server-bootstrap-verified-deploy-20260807`
- Базовый commit: `848c91b62a5a1b4075a4659afd03cbc6fcf5b3d5`

## Перед началом

### Цель

Разорвать self-update bootstrap loop Server Supervisor без ослабления immutable image policy: собрать и просканировать application image для exact merge SHA, получить GHCR digest и выполнить production deploy через уже существующую verified-image ветку старого `deploy/server/deploy.sh`.

### Исходный контекст

Production update operation `e06bcb64c2764cba` завершилась terminal `runtimeerror`. Protected diagnostic PR #697 подтвердил:

- production preflight и PostgreSQL dump прошли;
- checkout переключился на `056242d2ffdb3b8696d6d78c8f975459acba077d`;
- исполняемый shell продолжил старую версию `deploy/server/deploy.sh`, запущенную до checkout switch;
- в логе снова появилась старая строка `No verified image digest supplied; building local rollback image.`;
- затем повторилась ошибка `failed to solve: build tag cannot contain a digest`;
- rollback подтверждён: checkout вернулся на `0dceb104a8d5c6a1a25dda07c708b916f2e9439f`, bot стал healthy, server smoke прошёл.

PR #696 исправил fallback local-build branch в новой версии `deploy.sh`, но это исправление не может повлиять на уже запущенный старый shell в первом self-update переходе.

Старая версия `deploy.sh` уже умеет безопасную verified-image ветку при наличии `VELVET_DEPLOY_IMAGE`: она принимает только immutable `ghcr.io/stellmaria/velvet@sha256:<64 hex>`, pulls image и проверяет `org.opencontainers.image.revision` против target SHA. Поэтому bootstrap может обойти только проблемную local-build ветку, не обходя проверки revision/health/smoke.

### Планируемый объём

- добавить одноразово-триггеруемый workflow `.github/workflows/bootstrap-verified-production-deploy.yml`;
- trigger только при merge изменения самого workflow в `main`;
- checkout exact merge SHA;
- build image с OCI revision label равным `github.sha`;
- блокировать HIGH/CRITICAL findings через pinned Trivy action;
- push image в `ghcr.io/stellmaria/velvet`, resolve immutable digest и перепроверить revision label;
- перед production mutation проверить branch `main`, expected old HEAD `0dceb104...` и clean tracked checkout;
- вызвать старый production `deploy/server/deploy.sh` с `VELVET_DEPLOY_TARGET_SHA=<exact merge sha>` и `VELVET_DEPLOY_IMAGE=<verified digest>`;
- после deploy подтвердить exact target HEAD и clean checkout;
- не выполнять `reconcile coders` в этом workflow.

### Критерии готовности

- protected PR CI green на exact head;
- merge-triggered bootstrap workflow terminal `success`;
- GHCR digest соответствует exact merge SHA по OCI revision label;
- production deploy проходит verified-image ветку без local `compose build bot`;
- production HEAD равен exact merge SHA и checkout clean;
- deploy script health/smoke gates проходят;
- после этого coder reconcile выполняется отдельно по существующему owner-authorized Kael contract.

### Риски и ограничения

Workflow выполняет production mutation и package publish, поэтому scope жёстко ограничен собственным path-trigger, exact expected old production HEAD, immutable digest verification и существующим deploy script. Он не должен становиться общим auto-deploy механизмом для любых будущих main changes. Если production HEAD или dirty state отличаются от ожидаемых, workflow обязан fail closed до deploy.

## После завершения

### Фактически сделано

- добавлен `.github/workflows/bootstrap-verified-production-deploy.yml`;
- workflow builds revision-labelled image, scans HIGH/CRITICAL, pushes GHCR digest and validates OCI revision;
- production SSH step проверяет old HEAD/clean state, затем запускает existing deploy script только с explicit target SHA и verified image digest;
- post-deploy проверяется exact target HEAD и clean tracked checkout.

### Миграции и совместимость

Миграций данных и production env schema нет. Existing `.env.server` immutable `VELVET_IMAGE` policy не меняется. Existing deploy script verification, backup, rollback, health и smoke gates сохраняются.

### Проверки

До merge требуется полный protected CI на exact PR head. После merge требуется terminal result bootstrap workflow и проверка его production output.

### PR и commit

PR открывается после проверки полного diff относительно current `main`. Merge допускается только exact reviewed head после terminal green protected CI.

### Следующий шаг

После успешного bootstrap deploy подтвердить production HEAD/clean state, затем продолжить отдельно разрешённый `reconcile coders`, `coderctl health all` и typed read-only canary через Каэля.

### Незавершённое

- проверить branch diff;
- открыть PR;
- дождаться protected CI;
- merge exact head;
- получить terminal bootstrap workflow result;
- подтвердить production exact HEAD и health;
- продолжить coder reconcile/canary.