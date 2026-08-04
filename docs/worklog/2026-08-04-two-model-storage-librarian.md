# Сессия: двухмодельный Storage Librarian

- Дата: 2026-08-04
- ID: `9670e80c2398410eadc4ffe376c1eb81`
- Линия/фаза: Telegram Storage Librarian, production integration hardening
- Статус: `завершено`
- Ветка: `agent/9670e80c-two-model-storage-librarian`
- Базовый commit: `eb4849c3ee4461b540d3e1ba0572cf54f82a12d3`
- Tier contract: `task_type=code`, `complexity=complex`, `risk=high`, `mutation_policy=isolated_pr_only`, `requested_tier=high_risk`

## Перед началом

### Цель

Разделить анализ текста Storage и ответы `/storage_ask`: выполнять строгий структурированный текстовый анализ напрямую через private Ollama `/api/chat`, сохранив Hermes Runs API только для ответов по уже сохранённому индексу; одновременно подготовить, но не объявлять готовым, отдельный vision alias.

### Исходный контекст

`main` использует один `HermesRunsClient` и для анализа, и для ответов. Deploy-контур создаёт один локальный alias `velvet-librarian-local:v1` из `qwen3.5:9b-q4_K_M`. Массовая автоочередь по умолчанию выключена. Текущий checkout создан как отдельный clone актуального `origin/main`, потому что управляющий checkout имеет read-only `.git`.

### Планируемый объём

- сначала добавить failing regression tests для settings, request/response/error contracts и разделения клиентов;
- реализовать прямой Ollama analysis client со строгой JSON Schema и контролируемыми ошибками;
- явно разделить analysis client и answer client в application service/composition;
- подготовить text/vision Modelfile, idempotent start/install/Compose/env contracts без host ports;
- обновить runbook, smoke/preflight/contract tests и project notes;
- выполнить focused и repository quality checks, независимый high-risk review, commit/push, один PR и дождаться CI.

### Критерии готовности

- analysis использует только private Ollama `/api/chat`, `/storage_ask` сохраняет Hermes Runs API;
- строгая схема отклоняет malformed/incomplete ответы, transport failures отображаются контролируемо;
- defaults и overrides соответствуют handoff, `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` не меняется;
- deploy требует оба alias, не публикует Ollama host port и не удаляет volume;
- image support явно остаётся незавершённой до передачи image bytes;
- focused tests, compile/lint/quality и полный релевантный suite проходят;
- diff не содержит секретов/runtime-файлов/несвязанных изменений; открыт не более чем один PR.

### Риски и ограничения

Изменение затрагивает application, infrastructure и deploy contracts. CPU-only inference может быть медленным; mass enqueue остаётся выключенным. Vision model только подготавливается: существующий pipeline не передаёт image bytes, поэтому image support не считается готовой. Production, merge, restart и pull моделей в этой сессии запрещены.

### Допуск в режиме стабилизации

1. Улучшается существующая функция индексирования Telegram Storage.
2. Анализ становится дешевле, детерминированнее и изолированнее, а ошибки — наблюдаемыми.
3. Новая предметная область не добавляется: меняется provider boundary существующего Librarian.
4. Улучшение проверяется request/schema/error/service/deploy regression tests и quality gates.
5. Сохраняются use-case/repository границы, prompt-injection/redaction, protected kinds, manual-first rollout и Hermes answer path.

## После завершения

### Фактически сделано

- `StorageLibrarianService` получил разные `analysis_client` и `answer_client`;
- текстовый `process_once` переведён на прямой private Ollama `/api/chat`, а `/storage_ask` оставлен на Hermes Runs API;
- добавлен строгий request/response client с JSON Schema, bounded options, synthetic run ID, usage и контролируемыми transport/HTTP/JSON/schema errors;
- добавлены defaults/overrides text и vision моделей; `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` сохранён;
- прежний двусмысленный `Modelfile` заменён на `Modelfile.text` и `Modelfile.vision`;
- start/install/Compose готовят и проверяют оба alias без host ports и удаления persistent volume;
- документация явно фиксирует, что vision alias подготовлен, но image support не завершена до передачи image bytes;
- package/navigation inventories синхронизированы штатными генераторами;
- независимый high-risk review нашёл четыре blockers/gaps; для них добавлены regressions, исправления проверены повторным review, новых high-risk findings нет.

### Миграции и совместимость

SQL-миграций нет. Существующие queue/index records совместимы. Новые анализы получают `velvet-librarian:qwen3-4b-text:v4`; существующие результаты не переписываются. Hermes API key и answer path сохраняются. Массовая очередь остаётся выключенной.

### Проверки

- `python -m unittest ...` focused storage/deploy/generated/safety suites: 53 tests, OK;
- `KRITA_BRIDGE_DIR=/tmp/velvet-krita-9670e80c ... python -m unittest discover -s tests`: 2242 tests, OK, skipped=124;
- `python -m compileall -q velvet_bot deploy/hermes-librarian tests/test_storage_librarian_ollama.py`: OK;
- `bash -n deploy/hermes-librarian/start.sh deploy/hermes-librarian/install.sh`: OK;
- `python -m mypy`: 11 bounded source files, OK;
- `bandit -q -r` для нового client/application boundary: OK;
- package architecture, Telegram navigation, public repository safety и project notes contracts: OK;
- independent high-risk review + повторная проверка исправлений: blockers=0;
- GitHub CI для implementation head `98e096ecc831784525d3dd57ddb50fd8a1cdb7cb`: все checks passed (tests shards + aggregate, preflight, Docker build/contract, bounded mypy, project notes, branch protection, static/image/supply-chain security и CodeQL).

### PR и commit

Ветка `agent/9670e80c-two-model-storage-librarian`; implementation commit `98e096ecc831784525d3dd57ddb50fd8a1cdb7cb`; PR `https://github.com/Stellmaria/Velvet/pull/585`.

### Незавершённое

- production rollout и manual smoke запрещены в этой сессии и выполняются только после merge;
- image bytes pipeline не реализован, поэтому vision/image support не объявляется готовой;
- первый разрешённый rollout скачает обе source models и требует контроля RAM/swap/latency;

### Следующий шаг

После merge и отдельного разрешения владельца выполнить только описанные команды:

```bash
cd /srv/velvet
git pull --ff-only origin main
sudo bash deploy/hermes-librarian/install.sh
sudo docker compose --env-file .env.server -f deploy/hermes-librarian/compose.yaml exec -T ollama-librarian ollama show velvet-librarian-text:v1
sudo docker compose --env-file .env.server -f deploy/hermes-librarian/compose.yaml exec -T ollama-librarian ollama show velvet-librarian-vision:v1
```

Затем сохранить `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false`, выполнить один небольшой manual text smoke через `/storage_analyze ID`, проверить `/storage_digest`, `/storage_ask`, Hermes Reports, latency/RAM/swap и отсутствие provider usage. Vision smoke не выполнять до отдельного image-bytes pipeline.

### Routing и privileges

- `requested_tier=high_risk`; `task_type=code`; `complexity=complex`; `risk=high`; `mutation_policy=isolated_pr_only`;
- isolated workspace: `/workspace/task-9670e80c-storage-librarian`;
- `actual_route`: текущий orchestrated Codex runner; provider/model telemetry runner не предоставил, fallback не запускался;
- `mutation_started=true` после создания worklog/тестов;
- `production_privileges=false`; production access/write, Docker, systemd, merge, deploy и restart не выполнялись.
