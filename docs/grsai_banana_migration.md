# Nano Banana 2 и Pro через GRS AI

Фото-модели `nano-banana-2` и `nano-banana-pro` отправляются через единый GRS AI API. Seedream 5 Pro и видеомодели продолжают использовать Kie.ai. Очередь и внутренний тип задачи сохраняют старое имя `media.generate.kie` ради обратной совместимости с уже созданными заданиями.

## Переменные окружения

Добавьте в серверный `.env`:

```dotenv
GRS_API_KEY=replace_with_grs_api_key
GRS_BASE_URL=https://grsaiapi.com
GRS_NANO_BANANA_2_MODEL=nano-banana-2
GRS_NANO_BANANA_PRO_MODEL=nano-banana-pro

# Бюджетные оценки в USD-эквиваленте. Они используются только внутренним
# AI budget guard и должны быть выставлены по фактическому тарифу аккаунта.
GRS_NANO_BANANA_2_USD=0.02
GRS_NANO_BANANA_PRO_USD=0.03
```

Существующие переменные Kie остаются обязательными, потому что через Kie по-прежнему выполняются временная загрузка Telegram-референсов, Seedream 5 Pro и видео:

```dotenv
KIE_ENABLED=true
KIE_API_KEY=replace_with_kie_api_key
KIE_USD_TO_RUB=replace_with_budget_rate
```

## API-контракт

Создание задачи:

```http
POST {GRS_BASE_URL}/v1/api/generate
Authorization: Bearer {GRS_API_KEY}
Content-Type: application/json
```

```json
{
  "model": "nano-banana-2",
  "prompt": "...",
  "images": ["https://.../reference.jpg"],
  "aspectRatio": "9:16",
  "imageSize": "2K",
  "replyType": "json"
}
```

Проверка асинхронного результата:

```http
GET {GRS_BASE_URL}/v1/api/result?id={task_id}
Authorization: Bearer {GRS_API_KEY}
```

Клиент поддерживает как немедленный ответ `succeeded`, так и состояния ожидания с последующим polling. Внутри очереди GRS task id получает префикс `grs:`, чтобы он не смешивался с Kie task id.

## Референсы

GRS получает публичные временные URL в поле `images`. Бот сначала скачивает Telegram-файл и загружает его через существующий временный Kie upload endpoint. Это сохраняет текущую защиту от повторной загрузки и не добавляет недокументированный base64-формат в GRS-запрос.

## Развёртывание

1. Обновить код и зависимости обычным Supervisor-процессом.
2. Добавить `GRS_API_KEY` и проверить `GRS_BASE_URL` в серверном `.env`.
3. Перезапустить бота.
4. В разделе «Мяу → Создать» выполнить smoke-test для Nano Banana 2 и Nano Banana Pro сначала в 1K, затем проверить один запрос с референсом.
5. Проверить завершённую задачу: `model_alias` должен быть `nano_banana_2` или `nano_banana_pro`, а внешний `provider_task_id` должен начинаться с `grs:`. Поле provider и имя внутренней очереди пока сохраняют legacy-значение `kie` для совместимости с отчётами и уже созданными задачами.
