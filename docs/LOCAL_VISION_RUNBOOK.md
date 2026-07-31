# Local Vision server runbook

Связано с issue #505 и `docs/AI_VISION.md`.

## Ограничения

- `AI_VISION_ENABLED=false` и `AI_VISION_QUEUE_ENABLED=false` сохраняются до
  завершения benchmark и sensitive calibration;
- production VL runtime не имеет internet egress;
- модель скачивает только one-shot сервис `vision-model-loader`;
- исходные приватные изображения не используются для первого benchmark;
- заполненный `.env.server` не коммитится и имеет права `600`.

## 1. Проверить конфигурацию

Перенесите VL-переменные из `.env.vision-local.example` в существующий
`.env.server`, не заменяя Telegram, PostgreSQL и provider secrets.

```bash
cd /srv/velvet
chmod 600 .env.server

python scripts/server_preflight.py \
  --env-file .env.server \
  --hermes-env .env.hermes \
  --skip-host-tools
```

Для первого запуска должны оставаться:

```dotenv
AI_VISION_ENABLED=false
AI_VISION_QUEUE_ENABLED=false
VISION_MODEL=qwen3-vl:8b-instruct-q4_K_M
VISION_MODEL_EXPECTED_DIGEST=
```

## 2. Собрать images

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision \
  --profile vision-bootstrap \
  build vision-model-loader vision-runtime vision-gateway
```

## 3. Установить Q4 model

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision-bootstrap \
  run --rm vision-model-loader
```

Повторный запуск не скачивает уже установленную модель заново, если model ID и
ожидаемый digest совпадают.

## 4. Запустить runtime и gateway без включения bot Vision

Bot нужно пересоздать один раз, чтобы он получил internal `vision-front` network.
Это не включает AI-функции, пока `AI_VISION_ENABLED=false`.

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision \
  up -d --build bot vision-runtime vision-gateway
```

Проверить состояние:

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision \
  ps
```

Gateway health проверяется из bot-контейнера, поскольку host port намеренно не
публикуется:

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision \
  exec -T bot python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen(
    "http://vision-gateway:8080/health",
    timeout=10,
) as response:
    print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
PY
```

## 5. Закрепить model digest

Возьмите поле `digest` из health response и внесите его в `.env.server`:

```dotenv
VISION_MODEL_EXPECTED_DIGEST=<полный digest или достаточный уникальный prefix>
```

После этого пересоздайте runtime и gateway:

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision \
  up -d --force-recreate vision-runtime vision-gateway
```

Runtime и loader должны завершаться ошибкой при несовпадении digest.

## 6. Подготовить безопасное benchmark-изображение

Используйте нейтральное тестовое изображение без приватных данных:

```bash
install -m 600 /path/to/test-image.jpg \
  /srv/velvet/data/runtime/vision-benchmark.jpg
```

## 7. Выполнить Q4 benchmark

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision \
  exec -T bot python scripts/benchmark_vision_gateway.py \
    --endpoint http://vision-gateway:8080 \
    --image /app/runtime/vision-benchmark.jpg \
    --rounds 3 \
    --docker-container "" \
    --output /app/runtime/vision-benchmark-q4.json
```

Отдельно зафиксируйте host/container stats во время запроса:

```bash
docker stats --no-stream \
  velvet-bot-1 \
  velvet-postgres-1 \
  velvet-hermes-1 \
  velvet-vision-runtime-1 \
  velvet-vision-gateway-1
```

## 8. Проверить Q8 candidate

В `.env.server` временно замените model ID одновременно во всех local VL полях:

```dotenv
VISION_MODEL=qwen3-vl:8b-instruct-q8_0
VISION_MODEL_EXPECTED_DIGEST=
AI_VISION_MODEL=qwen3-vl:8b-instruct-q8_0
AI_VISION_FLASH_MODEL=qwen3-vl:8b-instruct-q8_0
AI_VISION_SENSITIVE_MODEL=qwen3-vl:8b-instruct-q8_0
AI_VISION_FALLBACK_MODEL=qwen3-vl:8b-instruct-q8_0
```

Затем повторите шаги установки, запуска, digest pin и benchmark. Результат
сохраните как `/app/runtime/vision-benchmark-q8.json`.

## 9. Resource gate

Q8 выбирается только если одновременно выполнены условия:

- нет OOM/restart-loop;
- суммарная RAM под нагрузкой не превышает 80%;
- Telegram polling и callbacks не деградируют;
- warm latency пригодна для пользовательского сценария;
- качество на контрольной выборке заметно лучше Q4;
- Hermes/PostgreSQL/bot сохраняют рабочий резерв CPU и RAM.

Если хотя бы один обязательный gate не проходит, production default остаётся Q4.

## 10. Не включать очередь преждевременно

После выбора модели разрешается одиночный standard smoke. Sensitive route и batch
queue включаются только после отдельного PR с classifier, `adult_confirmed` gate,
versioned sensitive schema и закрытым тестовым набором.
