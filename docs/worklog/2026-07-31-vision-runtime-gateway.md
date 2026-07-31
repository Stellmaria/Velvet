# Локальный VL runtime и internal gateway

- Дата: 2026-07-31
- ID: #505
- Линия/фаза: Hybrid AI / PR B
- Статус: частично
- Ветка: `feat/505-vision-runtime-gateway`
- Базовый commit: `07138a89fc2b2ae82a5a1ef9f500a041a102f4b5`

## Перед началом

### Цель

Добавить internal-only runtime и provider-neutral gateway для локальной Qwen3-VL,
не публикуя vendor endpoint и не включая Vision в production до benchmark.

### Исходный контекст

PR #506 добавил trusted provider `local_openai_compatible`, zero-cost metering и
server preflight guards. При этом Compose ещё не содержал inference runtime,
gateway, persistent model storage или воспроизводимый benchmark.

### Планируемый объём

- profile-gated `vision-model-loader`, `vision-runtime` и `vision-gateway`;
- отдельные front/back internal networks, чтобы bot не видел vendor runtime;
- one-shot egress только для установки модели;
- version-pinned runtime base image и model digest guard;
- persistent model volume без повторного pull на каждом restart;
- preprocessing изображений в памяти до 1280 px;
- один параллельный VL-запрос;
- health/model endpoints и benchmark script;
- Docker/security и unit contracts.

### Критерии готовности

- ни один VL-порт не публикуется на host;
- bot подключён только к gateway-side сети;
- production runtime не имеет internet egress;
- gateway не принимает remote image URLs и чужую model ID;
- raw image/prompt не попадают в обычные логи;
- модель сохраняется в `${VELVET_DATA_DIR}/vision`;
- Docker Compose validation/build и полный CI зелёные;
- `AI_VISION_ENABLED` остаётся false до live benchmark.

### Риски и ограничения

Первый model pull занимает несколько гигабайт и может быть долгим. PR не выбирает
Q8 только по размеру RAM: production model и digest фиксируются после сравнения
Q4/Q8 на VPS. NSFW classifier и sensitive schema относятся к следующему срезу.

## После завершения

### Фактически сделано

- добавлен one-shot `vision-model-loader`, единственный VL-сервис с egress;
- добавлен `vision-runtime` без public port и без internet-facing сети;
- добавлен unprivileged `vision-gateway` как единственный endpoint для bot;
- bot и runtime разделены internal front/back networks;
- model volume сохраняется в `${VELVET_DATA_DIR}/vision`;
- runtime не скачивает модель при старте и проверяет optional digest;
- gateway ограничивает model ID, payload fields, message parts и concurrency;
- remote image URLs запрещены, принимаются только JPEG/PNG/WebP data URI;
- изображения исправляются по EXIF, уменьшаются и перекодируются без EXIF/ICC;
- raw image, base64 и prompt не пишутся в обычные логи;
- добавлены health/models endpoints и воспроизводимый benchmark script;
- обновлены `.env.server.example`, `.env.vision-local.example`, canonical docs и
  production runbook;
- Docker workflow проверяет оба vision profiles и собирает gateway/runtime images;
- branch синхронизирована с актуальным `main` после PR #518/#520.

### Миграции и совместимость

PostgreSQL migration отсутствует. Vision profile и все bot AI-флаги выключены по
умолчанию. Существующий bot продолжает использовать fallback heuristics, пока
runtime не пройдёт живой benchmark и отдельную sensitive calibration.

### Проверки

- первый test run выявил слишком узкое ожидание текста ошибки runtime URL;
- contract test исправлен на проверку public HTTP host;
- после синхронизации с `main` запущен повторный полный CI;
- финальные результаты CI фиксируются перед переводом PR из draft.

### PR и commit

- PR: #519;
- актуальный head перед повторным CI фиксируется следующим успешным run.

### Незавершённое

- подтвердить зелёные test shards, type check, notes и Docker build;
- live Q4/Q8 benchmark;
- model digest pin на production;
- NSFW routing;
- structured sensitive profile;
- Venice RP smoke.

### Следующий шаг

Довести PR #519 до merge и выполнить контролируемый Q4 benchmark на VPS с
`AI_VISION_ENABLED=false`.
