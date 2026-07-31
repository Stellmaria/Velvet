# Глубокий ИИ-анализ изображений

## Текущая архитектура

Velvet использует provider-neutral Vision Router. Production provider
`ollama` по-прежнему запрещён: bot/domain не обращаются к vendor endpoint и не
зависят от Ollama API. Для локального inference добавлен отдельный trusted
provider:

```dotenv
AI_VISION_PROVIDER=local_openai_compatible
AI_VISION_BASE_URL=http://vision-gateway:8080/v1
```

`vision-gateway` предоставляет ограниченный OpenAI-compatible контракт, а
`vision-runtime` остаётся изолированной реализацией внутри Compose. Bot не видит
vendor runtime напрямую. Cloud provider `openai_compatible` сохраняется для
опционального Pro fallback.

До завершения server benchmark и sensitive calibration production-флаги остаются
выключенными:

```dotenv
AI_VISION_ENABLED=false
AI_VISION_QUEUE_ENABLED=false
```

Архив, visual fingerprint и безопасные fallback-эвристики продолжают работать.

## Server VL profile

Compose содержит три сервиса с разными границами:

- `vision-model-loader` — одноразовая установка модели с интернет-доступом;
- `vision-runtime` — CPU inference без опубликованного порта и без egress-сети;
- `vision-gateway` — единственная точка доступа bot к локальному VL.

Сначала собирается runtime и один раз загружается выбранная модель:

```bash
cd /srv/velvet

docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision-bootstrap \
  build vision-model-loader

docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision-bootstrap \
  run --rm vision-model-loader
```

После фиксации model digest запускается inference profile:

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision \
  up -d --build vision-runtime vision-gateway
```

`vision-runtime` не скачивает модель при старте. Если persistent model volume
пуст либо digest не совпадает, контейнер завершается с ошибкой. Это отделяет
сетевую установку весов от обработки приватных изображений.

## Модель и benchmark

Кандидаты issue #505:

- `qwen3-vl:8b-instruct-q4_K_M` — performance baseline;
- `qwen3-vl:8b-instruct-q8_0` — quality candidate.

В production одновременно используется только одна модель. Выбор выполняется по
живому CPU benchmark на VPS, а не только по тому, помещаются ли веса в RAM.
Проверяются cold/warm latency, memory, CPU, polling bot, отсутствие OOM и качество
на контрольной выборке.

Benchmark gateway:

```bash
python scripts/benchmark_vision_gateway.py \
  --endpoint http://127.0.0.1:8080 \
  --image /path/to/non-private-test-image.jpg \
  --rounds 3 \
  --output /tmp/vision-benchmark.json
```

Gateway не публикуется на host в production Compose. Для benchmark команду нужно
запускать из bot-контейнера/внутренней сети либо временного диагностического
контейнера без изменения production port contract.

## Локальный trusted provider

Минимальная конфигурация находится в `.env.vision-local.example`:

```dotenv
AI_VISION_ENABLED=false
AI_VISION_QUEUE_ENABLED=false
AI_VISION_PROVIDER=local_openai_compatible
AI_VISION_BASE_URL=http://vision-gateway:8080/v1
AI_VISION_MODEL=qwen3-vl:8b-instruct-q4_K_M
AI_VISION_FLASH_MODEL=qwen3-vl:8b-instruct-q4_K_M
AI_VISION_SENSITIVE_MODEL=qwen3-vl:8b-instruct-q4_K_M
AI_VISION_FLASH_INPUT_RUB_PER_1M=0
AI_VISION_FLASH_OUTPUT_RUB_PER_1M=0
AI_VISION_SENSITIVE_INPUT_RUB_PER_1M=0
AI_VISION_SENSITIVE_OUTPUT_RUB_PER_1M=0
```

Local provider:

- не требует API key;
- разрешает только allowlisted Compose hostname `vision-gateway`;
- запрещает public/loopback endpoints, URL credentials, query и fragment;
- имеет monetary cost `0`, но сохраняет usage, latency, model, route и outcome;
- не делает cloud fallback для sensitive-контента по умолчанию.

Cloud routes по-прежнему требуют API key и положительную input/output pricing.
При смене provider на уровне route нужен отдельный route base URL.

## Gateway security contract

`vision-gateway`:

- не принимает remote image URLs;
- принимает только base64 data URI JPEG/PNG/WebP;
- ограничивает request size, decoded image size и число изображений;
- исправляет EXIF orientation и повторно кодирует изображение без EXIF/ICC;
- уменьшает длинную сторону максимум до `VISION_MAX_IMAGE_SIDE`;
- разрешает только configured model ID;
- запрещает streaming;
- сериализует inference через `VISION_MAX_CONCURRENCY=1`;
- не пишет image/base64/prompt в обычные логи;
- не хранит временные файлы на диске.

## VL-каскад

Vision Router поддерживает роли:

- `FLASH` — основной локальный анализ;
- `PRO` — опциональный cloud fallback для standard low-confidence/error;
- `SENSITIVE` — отдельная локальная политика для подтверждённого взрослого
  материала.

Sensitive classifier, `adult_confirmed` gate и отдельная versioned schema ещё
реализуются следующим срезом #505. До их завершения локальный runtime не считается
готовым для автоматического +18 маршрута.

Порог перехода standard анализа к Pro задаётся через
`AI_VISION_CASCADE_CONFIDENCE_THRESHOLD`. Версия промта фиксируется в
`AI_VISION_PROMPT_VERSION`.

## Структурированный профиль

Целевой результат локального VL является versioned JSON-профилем, а не только
свободным описанием. Он должен содержать факты о subject, composition, pose,
camera, visibility, covering, environment, lighting, palette, mood,
uncertainties, generation risks и confidence.

Malformed output не должен сохраняться как успешный профиль. Cache key должен
учитывать fingerprint изображения, model digest, schema version, prompt version и
route.

## Изображение → промт

Image-to-Prompt формирует редакционный формат `Vᴇʟᴠᴇᴛ Sɪɢɴᴀᴛᴜʀᴇ` поверх
утверждённого visual profile:

- `ВАЖНО` и `СТРОГО`;
- технический блок;
- композиция и поза;
- лицо, взгляд, руки, тело и волосы;
- локация, фон и свет;
- палитра и Negative prompts.

Formatter не должен придумывать имена, татуировки, личные референсы, одежду,
наготу или формат `9:16`. Калибровка standard/sensitive Image-to-Prompt и Pose
Extractor отслеживается issue #414.

## Очередь и хранение

- исходник уменьшается максимум до 1280 px до inference;
- профиль сохраняется в PostgreSQL;
- повторный fingerprint/model/schema/prompt/route использует cache;
- локальный cache hit не создаёт новый monetary usage event;
- очередь включается только после одиночного server smoke-test и resource gate.

```dotenv
AI_VISION_QUEUE_ENABLED=true
AI_VISION_BATCH_PLAN_TTL_SECONDS=900
```

## Legacy Ollama

Следующие элементы остаются устаревшими и не возвращаются:

- `AI_VISION_PROVIDER=ollama` и `AI_TEXT_PROVIDER=ollama` в production env;
- прямой bot/domain вызов `/api/chat`, `/api/tags` или `127.0.0.1:11434`;
- Windows Ollama recovery и Supervisor UI;
- Qwen/Ollama-specific названия в пользовательском интерфейсе.

Использование Ollama внутри изолированного `vision-runtime` является
infrastructure implementation detail за `vision-gateway`, а не production
provider contract Velvet.
