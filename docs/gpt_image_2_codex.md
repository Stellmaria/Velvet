# GPT Image 2: Codex-first, live limit gate и двухключевой Byesu fallback

Функция добавляет в Ауф модель `GPT Image 2` с пользовательским выбором
GPT-5.6 Sol/Terra/Luna, reasoning effort, качества и пропорции.

## Базовый контракт

- режим `Только текст`: 0 референсов;
- режим `Фото + текст`: от 1 до 6 референсов;
- один референс: JPG, PNG или WEBP до 8 МБ;
- пользовательский промт: до 8000 символов;
- Codex всегда является первым маршрутом для 1K, 2K и 4K;
- Byesu допускается только при явно подтверждённом `subscription_limit` Codex;
- после начала creative tool execution автоматическая смена провайдера запрещена;
- Byesu использует два разных физических API key: один для анализа, второй для генерации.

## Маршрутизация

### Шаг 1. Live preflight Codex до генерации

Перед creative generation runtime читает свежие окна подписки через Codex
app-server. Проверка выполняется для любого выбранного качества: 1K, 2K или 4K.

Codex считается явно исчерпанным только при одном из подтверждённых сигналов:

- `rate_limit_reached_type` содержит активный тип достигнутого окна;
- окно `primary` или `secondary` имеет `used_percent >= 100`, а `resets_at`
  отсутствует либо находится в будущем.

Если snapshot неизвестен, timeout-ится, возвращает нераспознанный JSON или окно
меньше 100%, preflight работает fail-open и задача пробует Codex. Это сохраняет
Codex-first семантику и не превращает кратковременную проблему limit probe в
платную генерацию.

### Шаг 2A. Codex доступен

Если активное исчерпание не подтверждено:

1. выбранный Sol/Terra/Luna получает пользовательский промт и все референсы;
2. Codex вызывает встроенный `image_gen` ровно один раз для creative generation;
3. если выбран 1K, полученный artifact является финальным;
4. если выбран 2K или 4K, запускается **второй Codex/GPT pass уже после creative generation**;
5. второй pass не вызывает `image_gen`, не создаёт новую сцену и не меняет визуальный замысел;
6. второй pass запускает подготовленный локальный Pillow export и проверяет точный размер итогового файла;
7. пользователю выдаётся artifact только после успешного high-resolution export.

Целевые размеры high-resolution export используют длинную сторону:

- 2K: 2048 px;
- 4K: 3840 px.

Вторая сторона вычисляется из выбранной пропорции и приводится к чётному числу
пикселей. Например, 2K 16:9 даёт 2048×1152, а 4K 16:9 даёт 3840×2160.

Второй pass является export pass, а не второй creative generation. Это важно:
пользователь получает одну сгенерированную фотографию, а не вторую интерпретацию
того же промта с привычным модельным сюрпризом в лице, одежде или композиции.

### Шаг 2B. Codex явно исчерпан

Если live preflight подтверждает активный subscription limit, Codex creative
run не запускается. Запрос сразу идёт в Byesu fallback.

Если preflight был неубедителен, но сам Codex возвращает подтверждённый
`subscription_limit` **до первого tool execution**, разрешается один такой же
Byesu fallback. Lifecycle-события `thread.started` и `turn.started` не считаются
tool execution. Command/file/MCP/dynamic tool execution, существующий artifact
или неизвестный результат creative request блокируют fallback.

## Два Byesu ключа

### Hermes-Codex key

Переменная:

```env
BYESU_HERMES_CODEX_API_KEY=...
```

Этот физический API key используется для:

- Hermes / Kael / coder provider fallback после лимита Codex;
- Sol/Terra/Luna анализа GPT Image 2 при Byesu image fallback;
- `/v1/responses` image analysis.

Основной Hermes пока также читает legacy-переменную `OPENAI_API_KEY`, поэтому в
production обе переменные должны содержать **одно и то же физическое значение**:

```env
OPENAI_API_KEY=<Hermes-Codex key>
BYESU_HERMES_CODEX_API_KEY=<тот же Hermes-Codex key>
```

Это два env alias, но один физический ключ.

### Media Gen key

Переменная:

```env
BYESU_MEDIA_GEN_API_KEY=...
```

Это второй, отдельный физический API key. Он используется только для платных
image endpoints Byesu:

- `/v1/images/generations`;
- `/v1/images/edits`.

Runtime fail-closed проверяет, что Hermes-Codex и Media Gen keys различаются.
Перед canonical Compose lifecycle Media Gen key синхронизируется в уже
существующий `/srv/hermes-coders/secrets/velvet.env`; остальные project secrets
сохраняются. Max использует отдельный `max.env` и Media Gen key не получает.
Несекретный Compose wrapper по-прежнему не проецирует ни один API key и не
требует дополнительного env-файла для обычного `docker compose config`.

## Capability gate Byesu

Перед платной fallback generation runtime делает две независимые проверки
`GET /v1/models`:

- Hermes-Codex key должен видеть выбранный `gpt-5.6-sol`, `gpt-5.6-terra` или `gpt-5.6-luna`;
- Media Gen key должен видеть выбранный `gpt-image-2` или `firefly-gpt-image-2`.

Один ключ больше не обязан видеть одновременно текстовые и image-модели.
Именно это разделение устраняет прежний ложный blocker, при котором Media key
пытались использовать как общий Hermes credential или наоборот.

## Выбор Byesu generator после Codex limit

| Качество | Референсы | Генератор |
|---|---:|---|
| 1K | 0–3 | `gpt-image-2` |
| 1K | 4–6 | `firefly-gpt-image-2` |
| 2K | 0–6 | `firefly-gpt-image-2` |
| 4K | 0–6 | `firefly-gpt-image-2` |

Эта таблица применяется **только после решения перейти на Byesu из-за Codex
subscription limit**. Качество 2K/4K само по себе никогда не выбирает провайдера.

## Byesu analysis → generation

При fallback выбранный Sol/Terra/Luna на Hermes-Codex key анализирует исходный
промт и все референсы и возвращает один финальный generation prompt. Он должен:

- сохранить сцену, действие, стиль и ограничения пользователя;
- добавить устойчивые признаки внешности и разрешить противоречия референсов;
- не содержать рассуждения, варианты и отчёт об анализе;
- целиться максимум в 6500 символов;
- никогда не превышать 8000 символов.

После этого Media Gen key выполняет ровно одну image generation/edit операцию.
Если анализатор возвращает больше 8000 символов, generation не запускается.

## Production-конфигурация

```env
# Один физический Hermes-Codex key в двух совместимых alias:
OPENAI_API_KEY=<Hermes-Codex key>
BYESU_HERMES_CODEX_API_KEY=<тот же Hermes-Codex key>

# Второй физический ключ только для image generation:
BYESU_MEDIA_GEN_API_KEY=<Media Gen key>

CODEX_IMAGE_LIMIT_PREFLIGHT_ENABLED=true
CODEX_IMAGE_LIMIT_PREFLIGHT_TIMEOUT_SECONDS=3
CODEX_IMAGE_BYESU_FALLBACK_ENABLED=false
CODEX_IMAGE_BYESU_BASE_URL=https://byesu.com/v1
CODEX_IMAGE_BYESU_TIMEOUT_SECONDS=600
```

Fallback остаётся выключенным до успешного live capability smoke обоих ключей.
После этого оператор явно включает `CODEX_IMAGE_BYESU_FALLBACK_ENABLED=true` и
штатно reconciles coder runtime.

## Обязательные live smoke после rollout

1. Codex preflight ниже 100% продолжает Codex route для 1K, 2K и 4K.
2. Активные 100% пропускают Codex creative launch и выбирают Byesu.
3. Недоступный preflight fail-open пробует Codex.
4. Clean `subscription_limit` до tool execution разрешает ровно один fallback.
5. После любого creative tool execution Byesu fallback блокируется.
6. Codex 1K выполняет одну creative generation без high-res pass.
7. Codex 2K выполняет одну creative generation + отдельный non-creative GPT export pass и выдаёт фактические 2K pixels.
8. Codex 4K выполняет одну creative generation + отдельный non-creative GPT export pass и выдаёт фактические 4K pixels.
9. Hermes-Codex key видит Sol/Terra/Luna, Media Gen key видит обе image-модели.
10. Два физических Byesu key различаются.
11. Byesu fallback 1K проверяется с 0, 3, 4 и 6 референсами.
12. Byesu fallback 2K/4K проверяется как единая generation без Codex post-export.
13. Preview, оригинал и фактические пиксели сверяются после каждого high-res smoke.

CI может проверить routing, secret boundaries, exact export dimensions и lifecycle,
но не может доказать живой баланс подписки или provider model availability. Эти
пункты остаются production smoke-контрактом.
