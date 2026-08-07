# Сессия: read-only diagnostics Arthur Librarian reconcile

- Дата: 2026-08-07
- ID: `2026-08-07-arthur-production-reconcile-diagnostics`
- Линия/фаза: Arthur Librarian Phase 2 / production acceptance (#586)
- Статус: частично
- Ветка: `ops/arthur-librarian-reconcile-diagnostics`
- Базовый commit: `558f846040fed92ac3935f2fce2dcbd52a284946`
- PR: pending

## Перед началом

### Цель

Получить безопасное read-only production evidence точной причины падения `velvet-librarian.service` после successful canonical application deploy и accepted fixed-target Librarian reconcile, не выполняя ещё один speculative restart/deploy.

### Исходный контекст

Arthur rollout run `31191020196` успешно выполнил canonical `deploy/server/deploy.sh` на verified application source `e6571062af2c963297c17f94685490fa054c90ca` и immutable image `ghcr.io/stellmaria/velvet@sha256:517165ef91701ec7138ddb11a0138e6a2375d22a3a7683737b15ef7ea46c98d0`.

После deploy checkout был восстановлен на exact rollout SHA `558f846040fed92ac3935f2fce2dcbd52a284946`. Fixed-target `reconcilectl submit librarian` был принят как task `reconcile_ef81a87a43e243a1b6fba648a518598c`, но завершился `failed`: installer дошёл до Brain Vault/context/profile/local-only checks и затем `systemctl restart velvet-librarian.service` вернул error.

Поскольку reconcile не завершился, автоматические Arthur health/ports/heartbeat/Ollama/getMe gates не выполнялись. #586 остаётся открытой.

### Планируемый объём

- добавить одноразовый push-triggered production diagnostics workflow;
- использовать только существующие deploy SSH credentials, без Arthur token/gateway secrets;
- выполнять только read-only host/systemd/Docker/Ollama/resource commands;
- не читать и не выводить `.env.server`;
- пропускать systemd/journal output через дополнительный redactor;
- сохранить ту же `velvet-production` concurrency group, чтобы probe не пересекался с deploy;
- после evidence удалить/закрыть diagnostics scope отдельным follow-up, а runtime fix делать только по подтверждённой причине.

### Критерии готовности

- protected CI diagnostics PR зелёный;
- probe запускается после merge и не выполняет production mutation;
- зафиксированы exact checkout SHA, unit result/status, bounded recent journal, Compose/container state, локальные Ollama model names и disk/RAM/swap;
- secrets/tokens/connection credentials не публикуются;
- evidence достаточно, чтобы выбрать bounded runtime fix без повторного speculative deploy.

### Риски и ограничения

System journal потенциально содержит application output, поэтому workflow применяет дополнительную redaction для bearer/token/api-key/password, Telegram-token shape, GitHub tokens и PostgreSQL credentials. Probe не запускает systemctl restart/start/stop, Docker create/restart/pull, model pull или reconcile. Vision implementation не входит в scope; #630 остаётся владельцем VLM runtime/model selection.

## После завершения

### Фактически сделано

Подготовлен `.github/workflows/arthur-production-diagnostics.yml`. Workflow сериализован общей production concurrency group и выполняет через SSH только read-only проверки: Git checkout, `systemctl show/status`, bounded `journalctl`, Compose `ps`, `docker inspect`, `ollama list`, `df`, `free` и `swapon`.

### Миграции и совместимость

SQL/application migrations отсутствуют. Production application image/source pair не меняется. Diagnostics workflow не вызывает canonical deploy или reconcile и не изменяет production runtime.

### Проверки

Локальный production evidence ещё не получен: workflow запускается только после protected CI и merge. Redaction выполняется до вывода systemd/journal evidence в Actions log; `.env.server` используется Compose только как input и не печатается.

### PR и commit

- Ветка: `ops/arthur-librarian-reconcile-diagnostics`.
- База: `558f846040fed92ac3935f2fce2dcbd52a284946`.
- Diagnostics workflow commit: `4a647c1823130d150760fecede3eaeb92c784f51`.

### Незавершённое

- открыть PR и пройти protected CI;
- merge только если current `main` не требует rebase;
- разобрать production diagnostics log;
- реализовать bounded fix фактической причины systemd startup failure;
- повторить canonical fixed-target reconcile и automated Arthur gates;
- затем выполнить manual live acceptance #586.

### Следующий шаг

Открыть diagnostics PR, дождаться зелёного CI, выполнить read-only production probe и использовать его redacted evidence как единственный источник для следующего runtime remediation slice.
