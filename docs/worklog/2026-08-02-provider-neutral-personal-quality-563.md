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

Общий `VisionCascadeRouter` уже поддерживал flash/pro/sensitive routes, OpenAI-compatible и local providers, единый `AIRequestExecutor`, token/cost ledger и content-hash cache. Personal quality при этом создавал отдельный прямой `QualityVisionClient`, обходил общий ledger/cache и сохранял provider/model, выбранные до выполнения, а не фактический fallback route.

### Планируемый объём

- добавить generic structured analysis contract для общего metered provider client;
- подключить canonical quality prompt/schema/normalizer как `personal-quality` contract;
- построить flash/pro cascade поверх общего `AIUsageService` и cache repository;
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
- tests, type check, Docker, security и project notes зелёные на merge head.

### Риски и ограничения

Quality JSON contract отличается от semantic-profile schema, поэтому provider client должен оставлять semantic behavior совместимым. Общий cascade не должен раскрывать route metadata пользователю и не должен автоматически использовать cloud sensitive route. Live provider acceptance не входит в этот code slice и остаётся в #410/#562.

## После завершения

### Фактически сделано

- добавлен generic `VisionAnalysisContract` для prompt, schema, normalizer и max tokens;
- общий `MeteredVisionClient` переведён на contract-driven structured requests с совместимым Ollama JSON fallback;
- `VisionCascadeRouter` использует contract schema version в cache key и возвращает фактические route metadata;
- factory строит semantic и personal-quality routes поверх общих adapters, ledger и cache;
- canonical quality prompt/schema/normalizer переиспользуются через `build_quality_vision_contract()`;
- `WorkspaceQwenQualityService` использует cascade result, actual provider/model и bounded workspace/media metadata;
- repository сохраняет фактический route и отклоняет отсутствующую `(workspace_id, media_id)` до rework transitions;
- composition сохраняет user-facing module key `qwen` и worker lifecycle, но удаляет прямой personal `QualityVisionClient`;
- исправлен regression в `_route_config`: helper использует собственный аргумент `prompt_version`, а не локальную переменную factory;
- обновлены reviewed architecture fingerprints и канонические repository/package inventories;
- добавлены unit, cache, service и PostgreSQL two-workspace isolation contracts.

### Миграции и совместимость

Новых миграций нет. Существующие `provider` и `model` в `workspace_qwen_checks` теперь отражают фактически принятый flash/pro/cache result. System `CalibratedAIQualityService`, Telegram callbacks и module key `qwen` остаются совместимыми.

### Проверки

На ветке выполнен verified evidence run:

```bash
python -m compileall -q main.py velvet_bot scripts tests
python scripts/inventory_repository_layout.py \
  --check \
  --label p3e-repository-layout-complete
python scripts/inventory_package_architecture.py \
  --check \
  --label p1-package-architecture-baseline
python -m unittest \
  tests.test_local_vision_provider_contract \
  tests.test_workspace_personal_quality_route \
  tests.test_workspace_qwen_product \
  tests.test_vision_cascade_router \
  tests.test_p3e_repository_layout_inventory \
  tests.test_package_architecture_inventory -v
python scripts/ci_preflight.py
```

Все перечисленные проверки прошли до фиксации evidence. Финальный merge допускается только после зелёных full tests, type check, Docker, security supply chain и project notes contract на чистом head без временной write-инфраструктуры.

### PR и commit

- PR: #565 `P1: provider-neutral personal quality route`;
- merge method: squash;
- merge защищён exact-head SHA guard;
- временный `contents: write` job и одноразовый refresh helper удаляются до финального CI.

### Незавершённое

В рамках code slice незавершённых изменений нет. Live cloud-provider smoke, Telegram role acceptance и production workspace проверка остаются отдельными эксплуатационными задачами #410/#561/#562 и не закрываются данным merge.

### Следующий шаг

Провести bounded live acceptance из #410/#561/#562 на production-конфигурации без расширения provider credentials и без изменения system Quality Center.
