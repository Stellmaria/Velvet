# Сессия: Phase 1 hardening Артура Librarian

- Дата: 2026-08-04
- ID: `arthur-librarian-phase1-20260804`
- Линия/фаза: Telegram Storage Librarian, production safety hardening
- Статус: `частично`
- Ветка: `fix/arthur-librarian-phase1`
- Базовый commit: `2827fb7aba72c0447f16ddf05383745a9276e9bd`
- Связанное issue: `#586`

## Перед началом

### Цель

Исправить уже вошедший в `main` двухмодельный Storage Librarian до безопасного text-only rollout: запретить silent truncation, проверять штатное завершение Ollama, корректно записывать analyzer, разделить terminal/retryable failures, ограничить одновременную загрузку моделей и проверять реальный bot-to-Ollama маршрут после установки.

### Исходный контекст

Двухмодельная интеграция из PR #585 уже находится в `main`, но исходный PR остался открытым и конфликтующим. Независимая проверка выявила эксплуатационные блокеры: вход до 120000 символов при `num_ctx=8192`, отсутствие проверки `done_reason`, `OLLAMA_MAX_LOADED_MODELS=2`, запись `analyzer='hermes'` для прямого Ollama, prompt с якорем `confidence=0`, повторение deterministic failures и installer health только через Hermes.

### Планируемый объём

- ввести terminal error contract и не повторять неизменяемые validation failures;
- fail closed для prompt, который не помещается в bounded context;
- принимать completed только при `done=true` и `done_reason=stop`;
- сохранять фактический analyzer;
- потребовать русский natural-language output и убрать нулевой confidence anchor;
- оставить одновременно загруженной только одну Ollama-модель;
- не выполнять source pull при уже заполненном persistent volume;
- добавить post-install structured smoke из основного bot-контейнера в private Ollama;
- обновить focused regression tests.

### Критерии готовности

- oversized input не отправляется модели и не обрезается молча;
- `length`, missing completion state и schema mismatch завершаются terminal failure без retry;
- timeout/network/5xx остаются retryable;
- completed analysis хранит `analyzer=ollama`;
- text/vision aliases вытесняют друг друга при `OLLAMA_MAX_LOADED_MODELS=1`;
- installer проверяет фактический `bot -> ollama-librarian /api/chat` путь;
- auto enqueue и production rollout не включаются;
- focused tests, bash syntax и CI проходят.

### Риски и ограничения

Chunking в этой фазе не реализуется: большие документы завершаются явной terminal error до отдельного bounded chunking design. Vision image-byte pipeline и отдельный Telegram bot Артур относятся к следующим фазам issue #586. Production deploy и merge в этой сессии не выполняются.

## После завершения

### Фактически сделано

- добавлен `TerminalStorageLibrarianError` и явная analyzer metadata в run result;
- Ollama client получил conservative prompt bound, completion-state validation и terminal/retryable HTTP classification;
- prompt требует русский natural-language output и корректно определяет confidence;
- repository сохраняет фактический analyzer и поддерживает terminal fail без requeue;
- service отдельно обрабатывает terminal validation failures;
- Compose ограничен одной загруженной моделью;
- start script скачивает только отсутствующие source models;
- installer выполняет structured bot-to-Ollama smoke;
- добавлены regression tests для всех перечисленных контрактов;
- канонические package/P2 inventory перегенерированы: production LOC 141744, architecture violations 548, approved broad boundaries 106 из 106;
- package inventory записан с канонической меткой `p1-package-architecture-baseline`, которую использует CI;
- package baseline test обновлён на production LOC 141744;
- repository-layout inventory обновлён для нового test consumer `tests/test_storage_librarian_phase1_hardening.py`.

### Миграции и совместимость

SQL migration не требуется: поле `analyzer` уже является `TEXT`. Старые записи не переписываются. Поле `hermes_run_id` сохраняется для совместимости и может содержать synthetic Ollama run ID. Auto enqueue остаётся выключенным.

### Проверки

- локальный isolated focused suite: 22 tests, OK;
- `python -m py_compile` для изменённых Python-файлов: OK;
- `bash -n` для `start.sh` и `install.sh`: OK;
- полный repository CI выполняется в draft PR #610.

### PR и commit

Ветка `fix/arthur-librarian-phase1`; draft PR `#610` пересобран от актуального `main`.

### Незавершённое

- обязательный GitHub CI и независимый review;
- production smoke Storage #2168;
- bounded chunking больших документов;
- отдельный Telegram bot Артур;
- image-byte vision pipeline;
- controlled archive batches 10 -> 25 -> 100.

### Следующий шаг

После зелёного CI и независимого review разрешить merge отдельным решением владельца. Затем выполнить канонический rollout через `opsctl`/`reconcilectl`, сохранить `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` и провести один manual text smoke.
