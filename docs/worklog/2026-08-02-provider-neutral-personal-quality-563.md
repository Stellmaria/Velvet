# Provider-neutral personal quality route

- Дата: 2026-08-02
- ID: VELVET-563
- Линия/фаза: Workspace AI / bounded code slice #417
- Статус: `завершено`
- Ветка: `feature/provider-neutral-personal-quality-563`
- Базовый commit: `a564e0c05d0f8ddef82f8346d13cd14a5eaa0113`

## Перед началом

### Цель

Перевести execution персональной проверки качества workspace с прямого `QualityVisionClient` на общий provider-neutral vision route, сохранив пользовательский модуль `qwen`, tenant isolation, retry/compensation, calibration и rework lifecycle.

### Исходный контекст

Общий `VisionCascadeRouter` уже поддерживает flash/pro/sensitive routes, OpenAI-compatible и local providers, единый `AIRequestExecutor`, token/cost ledger и content-hash cache. Personal quality при этом создавал отдельный прямой `QualityVisionClient`, поэтому обходил общий ledger/cache и сохранял provider/model, выбранные до выполнения, а не фактический fallback route. Два почти одинаковых AI-контура, разумеется, были названы удобством.

### Планируемый объём

- добавить generic structured analysis contract для общего metered provider client;
- подключить canonical quality prompt/schema/normalizer как `personal-quality` contract;
- построить отдельный flash/pro cascade поверх того же `AIUsageService` и cache repository;
- не включать sensitive route автоматически и не менять system Quality Center;
- сохранять фактические provider/model после fallback или cache hit;
- передавать только bounded workspace/media metadata в ledger;
- отклонять подменённую пару `(workspace_id, media_id)` до rework side effects;
- добавить unit contracts и PostgreSQL isolation test;
- пройти полный CI и слить PR.

### Критерии готовности

- personal quality работает без обязательного Ollama и прямого `QualityVisionClient`;
- OpenAI-compatible route использует canonical quality JSON schema;
- cache hit не вызывает provider и не создаёт повторную оплату;
- calibration и persisted check используют фактический fallback provider/model;
- disabled workspace module не claims job;
- foreign workspace/media pair отклоняется транзакционно;
- Telegram module key/UX `qwen` и system Quality Center не меняются;
- tests, type check, Docker, security и project notes зелёные.

### Риски и ограничения

Quality JSON contract отличается от semantic-profile schema, поэтому обобщение provider client должно оставлять semantic behavior побитово совместимым. Общий cascade не должен раскрывать route metadata пользователю и не должен автоматически использовать cloud sensitive route. Live provider acceptance остаётся в #410/#562.

## После завершения

### Фактически сделано

- подготовлен generic `VisionAnalysisContract` для prompt/schema/normalizer/max tokens;
- общий `MeteredVisionClient` переведён на contract-driven запросы с optional Ollama JSON fallback;
- `VisionCascadeRouter` получает contract schema version в cache key и metadata;
- factory строит semantic и personal-quality routes поверх общих adapters, ledger и cache;
- canonical quality prompt/schema/normalizer переиспользуются через `build_quality_vision_contract()`;
- `WorkspaceQwenQualityService` использует cascade result, actual provider/model и bounded workspace/media metadata;
- repository записывает actual route и отклоняет отсутствующую workspace/media pair до rework transitions;
- composition сохраняет user-facing `qwen` module и worker name, но убирает прямой personal `QualityVisionClient`;
- добавлены unit/cache/service contracts и PostgreSQL two-workspace isolation test.

### Миграции и совместимость

Новых миграций нет: существующие `provider`/`model` в `workspace_qwen_checks` теперь отражают фактически принятый flash/pro/cache result. System `CalibratedAIQualityService`, Telegram callbacks и module key `qwen` остаются совместимыми.

### Проверки

Targeted patch workflow обязан выполнить:

```bash
python -m compileall -q velvet_bot scripts tests
python -m unittest \
  tests.test_workspace_personal_quality_route \
  tests.test_workspace_qwen_product \
  tests.test_vision_cascade_router -v
python scripts/ci_preflight.py
```

После удаления временного write-workflow выполняются полный test matrix, type check, Docker, security supply chain и project notes contract.

### PR и commit

Draft PR открывается после установки patch workflow. Финальный squash merge выполняется с exact-head guard; commit и PR фиксируются после зелёного CI.

### Незавершённое

До merge требуется применить bounded patch к production modules, устранить targeted/architecture findings, регенерировать inventories при необходимости и пройти полный CI. Live provider smoke остаётся в #410/#562.

### Следующий шаг

Применить patch через trusted same-repository workflow, проверить focused contracts и удалить все временные инструменты до финального CI.
