# 2026-08-06 — GPT Image 2 worker final-stage registration

- Дата: 2026-08-06
- ID: `gpt-image-worker-final-stage`
- Линия/фаза: Ауф · GPT Image 2 · production worker composition
- Статус: частично
- Ветка: `fix/gpt-image-worker-final-stage`
- Базовый commit: `5cd04ae20bb0bb6099cc5be920eb1f844cf5b54d`

## Перед началом

### Цель

Гарантировать регистрацию production worker `codex-image-generation` после
завершения всей feature-composition, чтобы полностью claimable задачи
`media.generate.codex_image` забирались из очереди при
`CODEX_IMAGE_ENABLED=true`.

### Исходный контекст

Production deploy commit `5cd04ae2` прошёл успешно, bot и router были healthy,
контейнер видел `CODEX_IMAGE_ENABLED=true`, а SQL-проверка показала для задачи
`0cc227f6-a285-499a-bf86-572545971e80` значения `due=true`, `scope_ok=true`,
`task_type_ok=true`, `paused=false` и `claimable=true`.

При этом live-экран `/system` не содержал worker
`codex-image-generation`, а задача оставалась `queued` с `attempt_count=0`.
Предыдущий hotfix сохранял wrapper через известные builder assignments, но
регистрация всё ещё выполнялась до полной feature-composition и зависела от
идеального сохранения цепочки всеми последующими installers.

### Планируемый объём

- отложить финализацию GPT Image worker до вызова composed application runner;
- обернуть итоговый `app.workers.build_worker_manager` после всех feature stages;
- синхронизировать canonical builder references;
- исключить повторную регистрацию worker;
- добавить явный startup-log успешной регистрации;
- добавить regression test с заменой builders поздним feature installer;
- не менять payload, billing, router contract или строку queued-задачи.

### Критерии готовности

- delayed runner оборачивает последний feature builder;
- `bootstrap` и `app.workers` используют один итоговый GPT wrapper;
- startup содержит `Installed GPT Image 2 worker runtime`;
- `/system` показывает `GPT Image 2 через Codex Plus · одна генерация`;
- существующая claimable задача покидает `queued`;
- required CI зелёный и PR слит squash-методом.

### Риски и ограничения

- CI не выполняет платную генерацию;
- реальный Hermes/Codex runtime проверяется только после production deploy;
- после восстановления worker задача может завершиться конкретной runtime
  ошибкой, которая будет отдельным эксплуатационным сигналом.

## После завершения

### Фактически сделано

- GPT Image bootstrap теперь откладывает builder finalization до фактического
  запуска composed application runner;
- итоговый wrapper строится поверх последнего feature builder;
- добавлены duplicate guard и startup-log регистрации;
- regression test воспроизводит позднюю замену обеих builder references.

### Миграции и совместимость

- SQL-миграций нет;
- структура `ai_tasks`, payload и Telegram callback contracts не меняются;
- изменение касается только порядка runtime composition.

### Проверки

- Python compile для изменённых модулей;
- GPT Image contract regression;
- package architecture contracts;
- полный protected-branch CI.

### PR и commit

- PR: `#658`;
- merge commit фиксируется после зелёных required checks.

### Незавершённое

- синхронизировать architecture inventory при необходимости;
- пройти required CI;
- слить PR в `main`;
- выполнить production deploy;
- подтвердить worker и переход задачи из `queued`.

### Следующий шаг

Исправить замечания CI, дождаться всех required checks и выполнить squash merge.
