# 2026-08-06 — GPT Image 2 worker bootstrap chain hotfix

- Дата: 2026-08-06
- ID: `gpt-image-worker-bootstrap-chain`
- Линия/фаза: Ауф · GPT Image 2 · production worker bootstrap
- Статус: частично
- Ветка: `fix/gpt-image-worker-bootstrap-chain`
- Базовый commit: `094c77bf55f66c04d9e3e91824dba5e33bb38a5f`

## Перед началом

### Цель

Восстановить регистрацию production worker `codex-image-generation`, чтобы
уже поставленные и новые задачи `media.generate.codex_image` забирались из
очереди при `CODEX_IMAGE_ENABLED=true`.

### Исходный контекст

Production deploy прошёл успешно, router отвечал `200`, token и DNS были
валидны, а контейнер видел `CODEX_IMAGE_ENABLED=true`. При этом задача более
пяти часов оставалась `queued` с `attempt_count=0`, без lock и ошибок.

Ручная проверка показала, что `install_gpt_image_2_bootstrap()` отдельно
патчит `bootstrap.build_worker_manager`. Однако следующий feature installer
`install_auf_runtime_dispatcher()` строит свою цепочку через
`velvet_bot.app.workers.build_worker_manager` и затем переписывает bootstrap.
Поскольку GPT installer не обновлял canonical workers-module reference, его
wrapper терялся до фактического создания `WorkerManager`.

### Планируемый объём

- патчить GPT Image builder одновременно в `bootstrap` и `app.workers`;
- сохранить существующую цепочку последующих worker-manager wrappers;
- добавить regression test, воспроизводящий production порядок GPT bootstrap
  и Auf runtime installer;
- не менять очередь, payload, billing, router contract или данные задачи;
- пройти обязательный CI и выполнить squash merge.

### Критерии готовности

- после GPT installer обе module references указывают на один wrapper;
- Auf runtime wrapper замыкает GPT wrapper, а не stale base builder;
- существующие GPT Image UI, progress, rate limits и timing tests проходят;
- required CI зелёный;
- после production deploy queued задача переходит в `running` или `error`
  с конкретной runtime-причиной.

### Риски и ограничения

- hotfix не выполняет платную генерацию в CI;
- существующая queued задача будет обработана только после production restart;
- router/Hermes runtime ошибки, если они есть, проявятся после восстановления
  worker registration и будут отдельным эксплуатационным сигналом.

## После завершения

### Фактически сделано

- GPT Image bootstrap обновляет canonical `app.workers` и bootstrap references;
- последующие feature wrappers сохраняют GPT worker в цепочке;
- добавлен regression test production installer ordering.

### Миграции и совместимость

- SQL-миграций нет;
- структура задач и callback contracts не меняются;
- изменение касается только composition worker factory.

### Проверки

- focused GPT Image contract test;
- полный required CI после открытия PR.

### PR и commit

- PR и merge commit фиксируются после зелёных проверок.

### Незавершённое

- открыть PR;
- пройти required CI;
- слить в `main`;
- выполнить production deploy;
- подтвердить обработку задачи `0cc227f6-a285-499a-bf86-572545971e80`.

### Следующий шаг

Опубликовать hotfix-ветку, открыть PR и дождаться полного required CI.
