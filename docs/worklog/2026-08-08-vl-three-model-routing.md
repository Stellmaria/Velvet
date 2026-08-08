# VL three-model routing policy

- Дата: 2026-08-08
- ID: `2026-08-08-vl-three-model-routing`
- Линия/фаза: Velvet AI / VL, canonical routing policy
- Статус: `частично`
- Ветка: `feat/vl-three-model-routing`
- Базовый commit: `c2bbdb8f9c5fba0344e02228f81dec0ae8e85bea`

Связано: #630, #709, #712, #724, #417, #416.

## Перед началом

### Цель

Привести application router к утверждённому 3-model контракту #630 без преждевременного включения новых провайдеров: `LOCAL_MAIN` по умолчанию, optional `LOCAL_UNCENSORED` только для sensitive fallback, optional `CLOUD_PRO` только для standard escalation.

### Исходный контекст

До этого slice `VisionCascadeRouter` использовал технические имена `FLASH`, `PRO`, `SENSITIVE`. Standard route уже делал local-first -> optional pro при error/low-confidence, но sensitive route сразу вызывал `SENSITIVE`, обходя основную Qwen. Factory также мог создавать `PRO`/`SENSITIVE` по наличию model id, без отдельных enable flags.

Канонический #630 требует:
- ordinary standard -> `LOCAL_MAIN`;
- difficult standard -> `LOCAL_MAIN` -> `CLOUD_PRO` только при typed reason/policy;
- adult-confirmed sensitive -> сначала `LOCAL_MAIN`; `LOCAL_UNCENSORED` только при refusal/error/low-information или explicit owner request;
- private/sensitive не отправляются в cloud;
- новые routes fail-closed до benchmark/credentials/runtime readiness.

### Планируемый объём

- добавить `AI_VISION_CLOUD_PRO_ENABLED=false` и `AI_VISION_LOCAL_UNCENSORED_ENABLED=false` gates;
- создавать PRO/SENSITIVE clients только при соответствующем explicit enable;
- sensitive mode сначала вызывает main local client;
- fallback на uncensored только по typed local failure/low-confidence либо explicit `force_uncensored`;
- добавить explicit `force_pro` для owner standard escalation;
- запретить `force_pro` для sensitive;
- сохранить cache/ledger/schema contracts;
- обновить env examples и regression tests;
- runtime multi-model installation/switching оставить отдельным bounded deployment slice, поэтому uncensored gate остаётся false до него.

### Критерии готовности

- стандартный запрос всегда начинает с `LOCAL_MAIN`;
- cloud PRO отсутствует из router, пока feature flag false;
- sensitive uncensored отсутствует из router, пока feature flag false;
- sensitive successful/high-confidence main result не вызывает uncensored;
- refusal/error/low confidence main sensitive result вызывает uncensored, если route включён;
- sensitive никогда не вызывает PRO;
- explicit owner force routes валидируются fail-closed;
- required CI зелёный.

### Риски и ограничения

- пока local gateway допускает только один model id, `LOCAL_UNCENSORED` нельзя включать в production; этот PR фиксирует application policy, а не делает ложный enable;
- euphemism detection как отдельный classifier не вводится: в этом slice typed fallback основан на refusal/error/low-confidence или explicit owner action;
- cloud pricing/API key нужны только при реальном enable PRO;
- production acceptance остаётся после отдельного gateway/runtime multi-model slice.

### Стабилизационный допуск

1. Используется существующий provider-neutral router, новый vendor-specific client не добавляется.
2. Sensitive privacy становится строже, cloud route там отсутствует.
3. Новые routes fail-closed feature flags.
4. Поведение покрывается router/factory tests.
5. Runtime model lifecycle отделён от application routing.

## После завершения

### Фактически сделано

- `LOCAL_MAIN` теперь является первым application-level VL route и для standard, и для adult-confirmed sensitive анализа;
- для sensitive используется та же main model с отдельным sensitive prompt/schema contract, без появления четвёртой модели;
- `CLOUD_PRO` создаётся только при `AI_VISION_CLOUD_PRO_ENABLED=true` и используется исключительно для standard escalation;
- `LOCAL_UNCENSORED` создаётся только при `AI_VISION_LOCAL_UNCENSORED_ENABLED=true`, требует отдельную локальную model id и используется исключительно для sensitive fallback;
- cloud sensitive route запрещён независимо от legacy `AI_VISION_ALLOW_CLOUD_SENSITIVE`;
- owner `force_pro` и `force_uncensored` не обходят `LOCAL_MAIN`, а только требуют второй route после main attempt;
- forced-route cache lookup ограничен требуемой моделью, поэтому сохранённый main fallback не может ложно удовлетворить следующий explicit force request;
- workspace personal-quality router явно создаётся с `include_pro=False` и остаётся local-only даже при глобальном enable CLOUD_PRO;
- `.env.vision-local.example` и `.env.server.example` документируют fail-closed gates и не содержат фиктивно включённой uncensored модели;
- package architecture baseline пересобран штатным preview workflow после синхронизации с актуальным `main`.

### Миграции и совместимость

DB migration нет. Existing `FLASH` / `PRO` / `SENSITIVE` enum values и env prefixes сохранены как compatibility surface. Новые optional routes выключены по умолчанию, поэтому production после merge продолжает работать только через существующий `LOCAL_MAIN`, пока оператор отдельно не включит и не настроит дополнительный route. `AI_QUALITY_ENABLED=false` и single-inference runtime budget этим slice не меняются.

### Проверки

- расширены `tests/test_vision_cascade_router.py`: local-first standard/sensitive, refusal routing, low-confidence routing, privacy boundary, force routes, route-specific cache и fallback semantics;
- добавлен `tests/test_vl_three_model_factory.py`: default-off gates, explicit cloud pricing/provider contract, distinct/local-only uncensored contract и legacy cloud-sensitive rejection;
- первый CI выявил неверное ожидание transport alias: `local_openai_compatible` внутри `VisionClient` нормализуется в `openai_compatible`; тест исправлен так, чтобы проверять реальную local gateway boundary вместо внутреннего alias;
- package architecture preview пересобирает inventory/exemptions после изменения существующего монолитного worker fingerprint;
- required CI на финальном owner-authored head остаётся последним условием перед merge.

### PR и commit

- PR: #727 `Enforce canonical VL three-model routing policy`;
- branch: `feat/vl-three-model-routing`;
- merge с актуальным main выполнен в branch перед финальным CI;
- package architecture baseline генерируется отдельным bot commit;
- merge SHA будет доступен после required green checks.

### Незавершённое

- дождаться required green checks на финальном owner-authored head;
- слить #727 в `main` только после зелёного CI;
- не включать `CLOUD_PRO` и `LOCAL_UNCENSORED` в production этим PR;
- runtime multi-model install/switching и benchmark acceptance остаются отдельным следующим slice #630.

### Следующий шаг

После merge #727 перейти к bounded runtime/gateway multi-model lifecycle: install/pin candidate models, one-active-inference switching, readiness checks и benchmark harness без автоматического mass-backfill.
