# Local Vision server runbook

Канонический источник: issue #630 `VL: 3-model local-first vision-контур Velvet и Arthur Archive`.

## Production invariants

До отдельного owner decision сохраняются:

```dotenv
AI_VISION_ENABLED=false
AI_VISION_QUEUE_ENABLED=false
AI_QUALITY_ENABLED=false
AI_VISION_CLOUD_PRO_ENABLED=false
AI_VISION_LOCAL_UNCENSORED_ENABLED=false
```

Этот runbook проверяет только `LOCAL_MAIN`. Он не включает global quality worker, archive batch, `CLOUD_PRO` или `LOCAL_UNCENSORED` и не создаёт mass backfill.

Текущий production `LOCAL_MAIN`, подтверждённый диагностикой 2026-08-07:

```dotenv
VISION_MODEL=qwen3.5:9b
VISION_MODEL_EXPECTED_DIGEST=6488c96fa5fa
AI_VISION_MODEL=qwen3.5:9b
AI_VISION_FLASH_MODEL=qwen3.5:9b
```

`VISION_MODEL_EXPECTED_DIGEST` является prefix pin. `vision-model-loader` и `vision-gateway` fail-closed при несовпадении установленного digest.

## 1. Проверить конфигурацию

Заполненный `.env.server` не коммитится и должен иметь права `600`.

```bash
cd /srv/velvet
chmod 600 .env.server

python scripts/server_preflight.py \
  --env-file .env.server \
  --hermes-env .env.hermes \
  --skip-host-tools
```

Перед benchmark отдельно проверьте, что все пять feature flags из раздела выше остаются `false`.

## 2. Собрать runtime/gateway

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision \
  --profile vision-bootstrap \
  build vision-model-loader vision-runtime vision-gateway
```

Сохраните identity собранных images до benchmark:

```bash
docker image inspect velvet-vision-runtime:local \
  --format '{{json .RepoDigests}} {{.Id}}'

docker image inspect velvet-vision-gateway:local \
  --format '{{json .RepoDigests}} {{.Id}}'
```

Если image собран локально и `RepoDigests` пуст, в scorecard сохраняется immutable image ID. После публикации image должен быть закреплён registry digest.

## 3. Проверить model volume

Только `vision-model-loader` имеет egress. Production runtime сам веса не скачивает.

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision-bootstrap \
  run --rm vision-model-loader
```

Если установленная модель не соответствует prefix `6488c96fa5fa`, loader завершается ошибкой. Не очищайте model volume автоматически и не заменяйте модель на другой candidate в рамках этого smoke.

## 4. Запустить runtime/gateway без включения bot Vision

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision \
  up -d --build vision-runtime vision-gateway
```

Gateway не публикует host port. Проверка health выполняется через уже подключённый к `vision-front` bot-контейнер:

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

Обязательный результат:

- `status=healthy`;
- `model=qwen3.5:9b`;
- `digest` начинается с `6488c96fa5fa`;
- `max_concurrency=1`.

## 5. Подготовить closed evaluation image

Для первого smoke используйте нейтральное изображение без приватных данных. Один и тот же файл используется для всех output-cap runs.

```bash
install -m 600 /path/to/test-image.jpg \
  /srv/velvet/data/runtime/vision-benchmark.jpg
```

Не добавляйте evaluation image в git и не отправляйте его в cloud.

## 6. Запустить benchmark с host resource evidence

Harness запускается на host. HTTP-запрос к internal-only gateway проходит через `docker exec` в bot-контейнер, поэтому gateway port не открывается, а harness при этом видит host Docker stats, swap и runtime image identity.

Сначала определите фактические container names:

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose.server.yml \
  --profile vision ps --format json
```

Затем выполните одинаковый benchmark для output caps `384`, `512`, `768`. Пример для `512`:

```bash
python scripts/benchmark_vision_gateway.py \
  --endpoint http://vision-gateway:8080 \
  --request-container velvet-bot-1 \
  --docker-container velvet-vision-runtime-1 \
  --image /srv/velvet/data/runtime/vision-benchmark.jpg \
  --model qwen3.5:9b \
  --expected-digest 6488c96fa5fa \
  --max-output-tokens 512 \
  --rounds 5 \
  --cold-unload \
  --output /srv/velvet/data/runtime/vision-benchmark-qwen35-9b-cap512.json
```

Повторите с `--max-output-tokens 384` и `768`, меняя имя output-файла. `--cold-unload` выполняется один раз перед первой пробой каждого run; первая sample считается cold, последующие warm.

Если container names отличаются от примера, используйте фактические имена из `docker compose ps`.

## 7. Что обязан содержать scorecard

Harness автоматически сохраняет:

- benchmark contract version;
- model tag и runtime model digest;
- expected digest prefix;
- runtime container image ref / image ID / RepoDigests, если Docker их предоставляет;
- cold latency;
- warm p50/p95;
- completion-token throughput estimate, если provider вернул usage;
- peak runtime memory и CPU;
- peak host swap usage;
- success/failure rate;
- schema validity rate;
- per-sample errors и latency;
- применённый output cap.

Поля `manual_scorecard` заполняются после просмотра закрытого evaluation set:

- omissions;
- hallucinations;
- visual-quality accuracy;
- OCR accuracy;
- pose accuracy;
- composition accuracy;
- owner quality score.

`tokens_per_second_estimate` делит completion tokens на полную request latency. Это reproducible comparative metric, но не чистая decoder-only скорость Ollama.

## 8. Acceptance gate

`LOCAL_MAIN` не считается принятым только потому, что ответ получен один раз. Перед изменением production flags должны быть сохранены результаты benchmark и выполнены все условия:

- model/digest совпадают с pin;
- нет timeout/OOM/restart-loop;
- schema validity приемлема на closed set;
- warm p50/p95 приемлемы для выбранного сценария;
- peak RSS/swap/CPU оставляют рабочий резерв VPS;
- manual quality score и omissions/hallucinations задокументированы;
- output cap выбран по данным, а не по желанию получить JSON размером с семейную хронику.

Timeout `VISION_REQUEST_TIMEOUT_SECONDS=300` в этом phase не увеличивается. Сначала измеряются текущий contract и output caps.

## 9. Rollout после single-image acceptance

Benchmark сам ничего не ставит в очередь. После отдельного owner approval rollout остаётся:

1. single-image smoke;
2. controlled batch `10`;
3. controlled batch `25`;
4. controlled batch `100`;
5. mass backfill только отдельным owner decision и только при наличии evidence.

`AI_QUALITY_ENABLED=false` сохраняется, пока owner явно не разрешил соответствующий controlled quality run. Legacy rows не удаляются ради benchmark.

`LOCAL_UNCENSORED` и `CLOUD_PRO` имеют собственные benchmark/privacy/runtime gates и этим runbook не активируются.
