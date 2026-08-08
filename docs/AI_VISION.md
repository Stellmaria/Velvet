# Глубокий ИИ-анализ изображений

Канонический источник архитектуры VL/VLM: issue #630 `VL: 3-model local-first vision-контур Velvet и Arthur Archive`.

## Текущая архитектура

Velvet использует provider-neutral Vision Router и внутренний `vision-gateway`. Bot/domain не обращаются напрямую к Ollama API и не знают о lifecycle runtime.

```text
Telegram / Storage / Workspace
        ↓
vision-gateway
  validation / preprocessing / policy / schema / cache / metrics
        ↓
model router
        ├─ LOCAL_MAIN
        ├─ LOCAL_UNCENSORED   optional, local sensitive fallback
        └─ CLOUD_PRO          optional, standard escalation
```

Local-first является default. Sensitive/private изображения не уходят в cloud по умолчанию.

## Три роли #630

### LOCAL_MAIN

Текущий production baseline:

```dotenv
AI_VISION_PROVIDER=local_openai_compatible
AI_VISION_BASE_URL=http://vision-gateway:8080/v1
AI_VISION_MODEL=qwen3.5:9b
AI_VISION_FLASH_MODEL=qwen3.5:9b
VISION_MODEL=qwen3.5:9b
VISION_MODEL_EXPECTED_DIGEST=6488c96fa5fa
```

`FLASH` остаётся compatibility/config name для application route, но архитектурная роль называется `LOCAL_MAIN`.

LOCAL_MAIN первым обрабатывает обычные standard-запросы и adult-confirmed sensitive-запросы. Он должен возвращать versioned structured profile, а не свободный рассказ.

### LOCAL_UNCENSORED

Отдельная локальная модель для разрешённого sensitive fallback. Она не является default и не должна использоваться для обычного архива.

```dotenv
AI_VISION_LOCAL_UNCENSORED_ENABLED=false
```

Route остаётся fail-closed до отдельного model benchmark и безопасного runtime switching. Sensitive route никогда не использует `CLOUD_PRO`.

### CLOUD_PRO

Сильный optional cloud route только для standard escalation по typed reason и privacy/budget policy.

```dotenv
AI_VISION_CLOUD_PRO_ENABLED=false
```

Сам факт низкой скорости локальной модели, большой archive queue или sensitive content не разрешает cloud escalation.

## Production safety flags

После production incident global quality и массовый archive processing отделены от возможности использовать VL вообще.

```dotenv
AI_VISION_ENABLED=false
AI_VISION_QUEUE_ENABLED=false
AI_QUALITY_ENABLED=false
AI_VISION_CLOUD_PRO_ENABLED=false
AI_VISION_LOCAL_UNCENSORED_ENABLED=false
```

`AI_QUALITY_ENABLED` является отдельным fail-closed gate. Обычный worker больше не должен автоматически засевать весь `media_files` global quality rows. Controlled quality batches используют owner-controlled `plan -> explicit start` и лимиты `10 -> 25 -> 100`.

Mass backfill не является нормальным side effect включения Vision.

## Server VL profile

Compose содержит три сервиса с разными границами:

- `vision-model-loader` — one-shot установка pinned модели; единственный vision service с egress;
- `vision-runtime` — CPU inference без опубликованного порта и без internet-facing network;
- `vision-gateway` — единственная VL boundary, видимая bot.

Runtime ограничен одним одновременно загруженным/исполняемым local inference path. Production budget остаётся `VISION_MAX_CONCURRENCY=1`, runtime CPU limit `6.0`, RAM limit `12g`.

## Model identity contract

Production evidence 2026-08-07 подтвердил:

- model `qwen3.5:9b`;
- digest prefix `6488c96fa5fa`;
- CPU-only execution;
- около 1.8–2.2 output tokens/sec на текущем VPS;
- около 6 CPU под одним inference;
- около 10.4 GB runtime RAM;
- длинные outputs могут упираться в 300-second timeout.

`vision-model-loader` и `vision-gateway` проверяют `VISION_MODEL_EXPECTED_DIGEST` как prefix и fail-closed при drift.

Compose fallback также закреплён на canonical LOCAL_MAIN, чтобы отсутствие env-переменной не вернуло старый 8B default.

## Gateway security contract

`vision-gateway`:

- принимает только base64 data URI JPEG/PNG/WebP;
- не принимает remote image URLs;
- ограничивает request size, decoded image size и число изображений;
- исправляет EXIF orientation и перекодирует изображение без EXIF/ICC;
- уменьшает длинную сторону до configured limit;
- принимает только configured model ID;
- проверяет configured model digest через runtime tags;
- запрещает streaming;
- сериализует inference через `VISION_MAX_CONCURRENCY=1`;
- не должен писать image bytes/base64 в обычные логи.

## Structured profile и output budget

Quality/analysis contract должен оставаться bounded. Global quality output cap сейчас ограничен 512 tokens; более длинный output не является бесплатным качеством на CPU runtime и раньше регулярно превращался в 300-second timeout.

Для benchmark LOCAL_MAIN обязательна matrix output caps:

- 384;
- 512;
- 768.

Timeout сначала не увеличивается. Сначала измеряются schema validity, omissions/hallucinations и latency на одном evaluation set.

## Benchmark contract

`scripts/benchmark_vision_gateway.py` сохраняет reproducible scorecard:

- model tag и digest;
- runtime image ref/image ID/registry digests, когда доступны;
- cold latency;
- warm p50/p95;
- completion-token throughput estimate;
- peak runtime memory/CPU;
- peak host swap;
- schema validity;
- success/failure rate;
- per-sample outcomes;
- applied output cap;
- manual fields для omissions, hallucinations, visual-quality/OCR/pose/composition accuracy и owner quality score.

Production gateway не публикует host port. Для полного host resource scorecard harness может выполнять HTTP через `docker exec` в bot-контейнер (`--request-container`) и одновременно с host собирать Docker/runtime evidence.

Подробная процедура находится в `docs/LOCAL_VISION_RUNBOOK.md`.

## Queue и archive policy

Global quality processing не является implicit archive discovery.

После single-image acceptance rollout выполняется только в порядке:

1. single-image smoke;
2. controlled batch 10;
3. controlled batch 25;
4. controlled batch 100;
5. mass backfill только отдельным owner decision.

Существующие legacy rows не удаляются ради benchmark. Automatic mass backfill запрещён.

## Cache и reuse

Canonical visual profile должен сохранять model/digest/schema/prompt/route provenance. Повторный fingerprint/model/schema/prompt/route может использовать cache.

Specialized quality, Image-to-Prompt и Pose Extractor должны по возможности использовать уже сохранённый canonical profile вместо второго полного image inference.

## Image-to-Prompt

Image-to-Prompt формирует редакционный формат поверх утверждённого visual profile. Formatter не должен придумывать имена, татуировки, личные референсы, одежду, наготу или формат кадра, отсутствующие в profile.

## Legacy contracts

Не возвращаются как production architecture:

- прямой `AI_VISION_PROVIDER=ollama` из bot/domain;
- прямой bot/domain вызов `/api/chat`, `/api/tags` или localhost Ollama;
- старый #505 Q4-vs-Q8 план как source of truth;
- automatic global image backfill;
- cloud sensitive fallback по умолчанию.

Ollama внутри изолированного `vision-runtime` остаётся infrastructure implementation detail за `vision-gateway`.
