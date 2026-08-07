# Сессия: Hermes runtime guard и container-only Pillow boundary

- Дата: 2026-08-07
- ID: `2026-08-07-hermes-runtime-guard-pillow-boundary`
- Линия/фаза: Hermes / GPT Image 2 / production activation hotfix
- Статус: `частично`
- Ветка: `fix/hermes-runtime-guard-pillow-boundary`
- Базовый commit: `5bcfe3b0f4e725274b066bcdbff30b97c141c701`

## Перед началом

### Цель

Устранить production regression после PR #699 без установки Pillow в host Python и без ослабления container/runtime smoke.

### Исходный контекст

Production успешно обновлён до merge commit `5bcfe3b0f4e725274b066bcdbff30b97c141c701`. Новые Hermes-Codex и Media Gen credentials прошли live `/v1/models` capability check. Coder images успешно собрались с `python3-pil`, canonical preflight и sandbox preflight прошли.

`hermes-coders.service` затем упал в host-side `ExecStartPre=runtime_source_guard.py`. Guard запускает настоящий import graph через `/usr/bin/python3`, а новый `codex_image_high_res_export.py` импортирует `PIL`. Pillow намеренно установлен только внутри coder image, поэтому host Python вернул `ModuleNotFoundError: No module named 'PIL'`.

### Планируемый объём

- оставить Pillow только в coder image;
- не добавлять host package dependency;
- разрешить host source guard проверить внутренний import/monkey-patch graph с минимальным import stub для container-only `PIL`;
- сохранить реальные Pillow imports для container runtime;
- добавить regression coverage host/container dependency boundary;
- пройти protected CI до merge;
- после merge обновить production checkout и повторить canonical Hermes orchestration install.

### Критерии готовности

- `runtime_source_guard.py` не требует Pillow на VPS;
- guard по-прежнему fail-closed проверяет наличие и права runtime sources;
- internal import graph и install hooks по-прежнему импортируются/проверяются;
- coder image по-прежнему содержит настоящий `python3-pil`;
- protected CI зелёный;
- production `hermes-coders.service` проходит host guard после rollout.

## После завершения

### Фактически сделано

`runtime_source_guard.py` теперь перед internal import probe создаёт минимальные in-memory modules `PIL` и `PIL.Image`. Stub действует только внутри отдельного host-side guard subprocess и не меняет coder container environment.

Настоящий Pillow остаётся dependency `Dockerfile.coder` и используется `codex_image_high_res_export.py` во время high-resolution export. Container build/runtime smoke сохраняют ответственность за фактическую доступность Pillow.

`tests/test_hermes_runtime_source_guard.py` дополнен контрактом container-only Pillow stub и запуском реального internal import graph через guard.

### Проверки

Protected CI требуется на финальном head PR #701. Production повторно не активируется до terminal green CI и merge exact reviewed head.

### PR и commit

- PR: #701 `Fix Hermes runtime guard host Pillow dependency`.
- Ветка: `fix/hermes-runtime-guard-pillow-boundary`.
- Кодовый commit: `91e44ccbe64514db3a923a3a9e4aad8a08d7ad99`.
- Regression-test commit: `9001d6be5d590b04319b890570882200a615e5b0`.
- Документирующий commit создаётся этим изменением.
- Merge допустим только для exact reviewed head после terminal green protected CI и `behind_by=0`.

### Незавершённое

- дождаться terminal protected CI PR #701;
- перед merge подтвердить `behind_by=0` относительно current `main`;
- merge exact green head;
- выполнить штатный production `velvet update`;
- повторить `sudo bash deploy/hermes-orchestration/install.sh`;
- подтвердить `hermes-coders.service`, `hermes-coder-router.service`, provider smoke и bot-to-router DNS;
- только после этого включать Byesu image fallback и выполнять live GPT Image 2 smoke.
