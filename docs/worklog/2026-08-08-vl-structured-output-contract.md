# VL structured output and benchmark fail-closed contract

- Дата: 2026-08-08
- ID: `2026-08-08-vl-structured-output-contract`
- Линия/фаза: VL / canonical LOCAL_MAIN production benchmark hardening
- Статус: `частично`
- Ветка: `fix/vl-structured-output-contract`
- Базовый commit: `f1c6751549f61fe72757d816ea46d6bbcc94c045`

## Перед началом

### Цель

Закрыть дефекты, проявившиеся в изолированном production smoke canonical `LOCAL_MAIN=qwen3.5:9b`: модель завершила запрос до gateway deadline и вернула HTTP 200, но весь output cap 512 ушёл без непустого final `message.content`, а benchmark при этом записал `success_rate=0.0` и всё равно завершился process exit code 0.

### Исходный контекст

До изоляции два production smoke были загрязнены параллельным Storage Librarian inference и завершались gateway timeout. После временной изоляции известных Librarian initiators один `512 / 1 / no-cold` запрос прошёл без Librarian activity: gateway завершил его примерно за 254 секунды с HTTP 200, runtime сгенерировал ровно 512 completion tokens примерно по 2.36 tok/s, но benchmark увидел пустой final content.

Gateway уже пропускал `response_format`, но не фиксировал no-reasoning policy для dedicated bounded vision path. Benchmark просил JSON только текстовой инструкцией, container transport заворачивал typed HTTP status в generic error, а `main()` benchmark script безусловно возвращал 0 независимо от sample/schema failure. Production workflow также использовал внешний timeout 300 секунд, равный внутреннему gateway timeout, и artifact validator не требовал полного functional/schema success.

### Планируемый объём

- принудительно отключить reasoning на dedicated local VL gateway перед вызовом Ollama;
- не разрешать клиенту повышать reasoning budget через gateway request;
- добавить benchmark `response_format` с строгой JSON Schema для canonical scorecard shape;
- ужесточить локальную schema validation до exact keys/types/ranges;
- сохранять latency и completion usage для HTTP 200, даже если final content пуст или невалиден;
- сохранять top-level `HTTP 504` при container request вместо generic wrapper;
- возвращать non-zero benchmark exit code при transport/content или schema failure;
- развести gateway deadline 300 секунд и outer benchmark timeout 360 секунд;
- заставить production workflow fail-closed проверять exit code, success/failure rate, schema validity и каждый sample;
- сохранять benchmark artifact через `if: always()` даже при functional failure;
- добавить fail-closed gate `STORAGE_LIBRARIAN_AUTO_ENQUEUE=false` для production benchmark;
- не менять canonical model, digest, optional routes, queue/backfill policy или production runtime в этом PR.

### Критерии готовности

- sanitized gateway payload всегда содержит `reasoning_effort=none`;
- клиент не может подменить dedicated gateway reasoning policy;
- benchmark payload содержит OpenAI-compatible strict `json_schema` response format;
- invalid keys/types/confidence не проходят benchmark schema validation;
- typed `HTTP 504` не теряется при request через container;
- benchmark pass требует `success_rate=1.0`, `failure_rate=0.0`, `schema_validity_rate=1.0`;
- production workflow использует outer timeout 360 при неизменном gateway timeout 300;
- failed benchmark artifact остаётся доступным для диагностики;
- targeted regression tests зелёные;
- required GitHub CI зелёный на exact final head;
- перед merge ветка имеет `behind_by=0` относительно `main`.

### Риски и ограничения

`reasoning_effort=none` опирается на текущий Ollama OpenAI-compatible `/v1/chat/completions` contract для thinking models. Этот gateway намеренно является bounded vision/extraction path, поэтому reasoning здесь считается нежелательным расходом latency/output budget. Изменение не доказывает production quality до повторного live benchmark после deployment нового runtime/gateway image.

Strict JSON Schema применяется benchmark harness, а не навязывается всем произвольным vision consumers: production callers могут иметь свои output contracts. Общая межсервисная CPU arbitration между VL и Storage Librarian остаётся отдельной архитектурной задачей; этот PR только запрещает automatic Librarian enqueue во время canonical workflow benchmark и не создаёт shared host inference lease.

## После завершения

### Фактически сделано

Gateway фиксирует `reasoning_effort=none` после sanitization, при этом поле не входит в разрешённый входной набор и поэтому клиент не может переключить bounded LOCAL_MAIN path обратно в high-reasoning режим.

Benchmark получил строгую JSON Schema с exact полями `subjects`, `composition`, `lighting`, `palette`, `confidence`, `additionalProperties=false` и confidence 0..100. Локальная проверка синхронизирована с этим shape. Для HTTP 200 теперь сохраняются latency/completion counters даже при пустом final content.

Container request сохраняет typed HTTP status, benchmark process завершается non-zero при любом content/transport failure или schema validity ниже 100%. Production workflow использует outer timeout 360 секунд при сохранённом gateway policy 300 секунд, валидирует каждый sample и всегда пытается загрузить scorecard artifact.

### Миграции и совместимость

SQL migration не требуется. Canonical model/digest не меняются. API gateway остаётся OpenAI-compatible subset; новая политика только добавляет server-side `reasoning_effort=none` в outbound runtime payload. Клиентский `reasoning_effort` остаётся запрещённым unknown field, поэтому публичная входная поверхность не расширяется.

Workflow остаётся manual-only, serialized через `velvet-production` и не выполняет deploy, pull, compose up/restart, enqueue или model mutation.

### Проверки

Локально пройдены syntax compile изменённых Python файлов. Targeted unittest: 19 тестов gateway + benchmark зелёные; 7 workflow contract tests зелёные на изменённом workflow. YAML разбирается локальным parser без syntax error.

Официальный текущий Ollama OpenAI compatibility contract подтверждает поддержку `reasoning_effort` со значением `none`, а structured outputs документация подтверждает schema-backed structured output через OpenAI-compatible `response_format` для vision models.

Полный required GitHub CI выполняется на PR exact head после записи worklog. Live production benchmark в рамках этого PR не запускается: сначала нужен merge и отдельный deployment/acceptance шаг.

### PR и commit

Ветка: `fix/vl-structured-output-contract`. Базовый `main`: `f1c6751549f61fe72757d816ea46d6bbcc94c045`. Implementation выполнен отдельными GitHub commits через contents API; финальный PR head фиксируется перед required CI/merge.

### Незавершённое

- открыть PR и дождаться всех required checks на exact final head;
- если `main` продвинется, синхронизировать ветку без force-push и повторить CI;
- перед merge подтвердить `behind_by=0`;
- после merge отдельно собрать/опубликовать immutable image и выполнить controlled production `512 / 1 / no-cold` benchmark;
- после нового production evidence решить, нужен ли следующий cap 384/768;
- shared heavy-local-inference admission между VL и Storage Librarian остаётся отдельным follow-up.

### Следующий шаг

Открыть PR, исправлять только доказанные CI failures, затем слить exact green head в protected `main`. Production success не объявлять до отдельного deployment и повторного isolated benchmark.
