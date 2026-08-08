# Arthur lifecycle: preserve running bot image

- Дата: 2026-08-08
- ID: `arthur-preserve-running-image-20260808`
- Линия/фаза: production lifecycle / Storage Librarian
- Статус: `завершено`
- Ветка: `fix/arthur-preserve-running-image-20260808`
- Базовый commit: `a84724836bcc603f0e609d1f58e1f1776e6eae3a`
- Канонический VL источник: issue #630

## Перед началом

### Исходный контекст

Arthur lifecycle-скрипты `enable_afk.sh`, `enable_full_archive.sh` и `disable_afk.sh` меняли `.env.server`, затем выполняли `docker compose --env-file ... up -d --force-recreate bot`. Если `VELVET_IMAGE` в `.env.server` оставался на старом immutable digest, конфигурационное переключение Arthur могло пересоздать основной bot на старом application image. Это смешивало две разные операции: изменение Storage Librarian режима и application deployment.

### Цель

Сделать Arthur lifecycle configuration-only операцией: при любом enable/disable пересоздавать bot только из точного image ID, который уже запущен, и fail-closed прекращать операцию, если текущий image identity нельзя доказать.

### Планируемый объём

- вынести bot recreate в общий shell helper;
- брать текущий bot container через Compose и проверять, что он запущен;
- читать точный Docker `.Image` ID текущего container;
- временно тегировать этот image ID и передавать его в Compose через shell `VELVET_IMAGE` override, который не зависит от stale `.env.server` pin;
- использовать `--no-deps --force-recreate bot`, не затрагивая соседние сервисы;
- после recreate сравнивать новый `.Image` с исходным и fail-closed при несовпадении;
- перевести все три Arthur lifecycle-скрипта на helper;
- добавить regression contract-test.

### Критерии готовности

- Arthur enable/disable не выбирает application image из `.env.server`;
- точный running bot image ID сохраняется до и после recreate;
- отсутствие running bot или недоказанный image ID блокируют lifecycle toggle;
- stale `VELVET_IMAGE` не может откатить bot;
- соседние Compose dependencies не пересоздаются;
- protected CI зелёный на exact PR head;
- перед merge PR head не отстаёт от `main`.

### Риски и ограничения

- helper не является deployment mechanism и намеренно не умеет выбирать новый application image;
- если bot отсутствует, Arthur toggle требует сначала verified application deploy;
- изменение `.env.server` выполняется до recreate, как и раньше; если recreate затем fail-closed завершится ошибкой, env уже отражает запрошенный режим, но runtime его не применит до следующего успешного recreate/deploy;
- production rollout этого исправления выполняется отдельно после merge и verified image provenance.

## После завершения

### Фактически сделано

Добавлен `deploy/hermes-librarian/recreate_bot_preserving_image.sh`. Helper:

- находит текущий Compose bot container;
- требует `State.Running=true`;
- извлекает точный `.Image` вида `sha256:<64 hex>`;
- создаёт временный локальный tag на этот image ID;
- запускает только `bot` через `--no-deps --force-recreate` с process-level `VELVET_IMAGE` override;
- проверяет новый container и требует тот же `.Image` ID;
- удаляет временный tag через `trap`.

`enable_afk.sh`, `enable_full_archive.sh` и `disable_afk.sh` больше не выполняют прямой bot recreate и используют общий helper.

Добавлен `tests/test_arthur_lifecycle_image_preservation.py`, который запрещает возврат прямого recreate в toggle-скрипты и фиксирует exact-image preservation contract.

### Миграции и совместимость

SQL migrations отсутствуют. Storage schema, Arthur jobs, VL queue и model configuration не меняются. Новых обязательных env vars нет. Existing `.env.server` pin сохраняется как deployment configuration, но больше не используется Arthur lifecycle для выбора другого application image.

### Проверки

CI выполняется после открытия PR. Merge допускается только при terminal success required checks на exact head и `behind_by=0`.

### PR и commit

PR #743. Финальный exact head фиксируется после terminal success CI. Production deploy выполняется отдельно.

### Незавершённое

- protected CI ещё должен завершиться на exact head;
- PR ещё не merged;
- production ещё не обновлён этим fix.

### Следующий шаг

Дождаться terminal success required CI, проверить актуальный `main` и `behind_by=0`, выполнить squash merge с expected head SHA. После merge перейти к production console: доказать текущий image/revision, выполнить verified deployment нового `main`, затем включить Arthur full-archive и подтвердить, что lifecycle toggle сохраняет exact bot image ID.
