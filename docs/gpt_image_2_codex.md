# GPT Image 2: Codex-first через dynamic availability и двухключевой Byesu fallback

Функция добавляет в Ауф модель `GPT Image 2` с пользовательским выбором
GPT-5.6 Sol/Terra/Luna, reasoning effort, качества и пропорции.

## Базовый контракт

- режим `Только текст`: 0 референсов;
- режим `Фото + текст`: от 1 до 6 референсов;
- один референс: JPG, PNG или WEBP до 8 МБ;
- пользовательский промт: до 8000 символов;
- 1K, 2K и 4K используют один и тот же динамический Codex availability gate;
- primary Codex route разрешён только когда persisted `codex_available=true`;
- при `codex_available=false` Codex не запускается, запрос сразу использует настроенный Byesu fallback;
- после начала creative tool execution автоматическая смена провайдера запрещена;
- Byesu использует два разных физических API key: один для анализа, второй для генерации.

## Единый Codex availability state

Каждый coder project хранит собственный state в writable `/opt/codex-runs`:

```json
{
  "codex_available": true,
  "codex_available_at": null,
  "provider_available": true,
  "reason": "available",
  "last_checked_at": 0,
  "next_periodic_check_at": 0,
  "manual_hold": false,
  "manual_hold_until": null,
  "rate_limits": {}
}
```

State хранится отдельно для Velvet и Max, потому что они используют отдельные
Codex auth homes. Один общий subscription pool между ними не предполагается без
отдельного доказательства идентичности аккаунта.

Environment variable не является источником runtime-state: environment уже
запущенного процесса нельзя безопасно переключить из отдельной operator command.
JSON-state пишется атомарно и читается непосредственно перед решением о маршруте.

## Как обновляется dynamic flag

### Обязательная пятичасовая проверка

При старте coder runtime выполняет live `account/rateLimits/read`, затем такой же
тихий probe выполняется **каждые 5 часов независимо от известного `resets_at`**.
Дополнительные operator refresh или проверки в момент ожидаемого восстановления
не сдвигают этот пятичасовой цикл.

Это намеренно. Если provider раньше указанного срока сбросил недельную квоту,
следующая обязательная пятичасовая проверка увидит фактическое состояние и
немедленно вернёт `codex_available=true`.

Локально watcher перечитывает state-файл раз в минуту, чтобы замечать изменения
от operator CLI. Это чтение файла не вызывает OpenAI и не увеличивает частоту
provider quota probes.

### Проверка в `codex_available_at`

Если live snapshot показывает активный limit и содержит будущий `resets_at`,
runtime сохраняет ожидаемое время как `codex_available_at`. Когда это время
наступает, выполняется дополнительный live probe. Если квота восстановлена,
флаг становится `true` сразу, не дожидаясь следующего пятичасового цикла.

Если исчерпаны несколько окон, ожидаемое восстановление берётся по более позднему
из блокирующих `resets_at`, потому что восстановление только одного окна ещё не
делает subscription доступной.

### Реальный `subscription_limit`

Если `codex_available=true`, но сам Codex execution всё же возвращает
`subscription_limit` до начала запрещающего fallback execution evidence:

1. persisted flag немедленно становится `false`;
2. следующая задача уже не пытается запускать Codex;
3. runtime делает best-effort live quota probe, чтобы сохранить актуальный
   `resets_at` в `codex_available_at`;
4. этот диагностический probe не имеет права немедленно вернуть flag в `true`,
   если он противоречит только что полученному execution failure;
5. вернуть `true` сможет следующая независимая успешная проверка: periodic 5h,
   provider-reset probe или operator refresh.

## Ручное управление

Внутри каждого coder runtime доступна команда:

```bash
python /app/codex_availability_ctl.py status
python /app/codex_availability_ctl.py refresh
python /app/codex_availability_ctl.py hold --until auto
python /app/codex_availability_ctl.py hold --until 2026-08-09T05:00:00Z
python /app/codex_availability_ctl.py clear
```

`hold --until auto` выполняет live probe и берёт реальный provider `resets_at`.
Если provider не сообщает активный limit или дату восстановления, команда требует
явный ISO-8601/Unix timestamp.

`clear` не выставляет `true` вслепую. Он снимает manual hold, временно переводит
provider-state в unknown и сразу выполняет live refresh. Codex разрешается только
если этот refresh подтверждает доступность.

## Маршрутизация GPT Image 2

### `codex_available=true`

1. выбранный Sol/Terra/Luna получает пользовательский промт и все референсы;
2. Codex вызывает встроенный `image_gen` ровно один раз для creative generation;
3. если выбран 1K, полученный artifact является финальным;
4. если выбран 2K или 4K, запускается второй Codex/GPT pass после creative generation;
5. второй pass не вызывает `image_gen`, не создаёт новую сцену и не меняет визуальный замысел;
6. второй pass запускает локальный Pillow export и проверяет точный размер итогового файла;
7. пользователю выдаётся artifact только после успешного high-resolution export.

Целевые размеры high-resolution export используют длинную сторону:

- 2K: 2048 px;
- 4K: 3840 px.

Вторая сторона вычисляется из выбранной пропорции и приводится к чётному числу
пикселей. Например, 2K 16:9 даёт 2048×1152, а 4K 16:9 даёт 3840×2160.

Второй pass является export pass, а не второй creative generation.

### `codex_available=false`

Codex creative run не запускается. Если Byesu image fallback включён, запрос
сразу идёт в Byesu. Если fallback отключён, задача fail-closed завершается без
попытки Codex.

Причиной false может быть подтверждённый subscription limit, operator manual
hold или ещё не подтверждённое состояние после старта/ошибки probe. Это новое
правило сознательно делает persisted dynamic flag единственным разрешением на
primary Codex route.

## Kael и coder-задачи

Тот же state используется обычным provider-chain, поэтому coder delegation Каэля,
Velvet coder и Max coder подчиняются той же развилке:

```text
codex_available=true  -> Codex subscription first
codex_available=false -> skip Codex -> configured Byesu coder route
```

Таким образом GPT Image 2 и coder-задачи больше не имеют независимых представлений
о доступности подписки.

## Два Byesu ключа

### Hermes-Codex key

Переменная:

```env
BYESU_HERMES_CODEX_API_KEY=...
```

Этот физический API key используется для:

- Hermes / Kael / coder provider fallback;
- Sol/Terra/Luna анализа GPT Image 2 при Byesu image fallback;
- `/v1/responses` image analysis.

Основной Hermes пока также читает legacy-переменную `OPENAI_API_KEY`, поэтому в
production обе переменные должны содержать одно и то же физическое значение.

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
Media Gen хранится только в operator `.env.hermes`. Узкий
`compose_image_runtime_env.py` передаёт его только `hermes-coder-velvet`.

## Capability gate Byesu

Перед платной fallback generation runtime делает две независимые проверки
`GET /v1/models`:

- Hermes-Codex key должен видеть выбранный `gpt-5.6-sol`, `gpt-5.6-terra` или `gpt-5.6-luna`;
- Media Gen key должен видеть выбранный `gpt-image-2` или `firefly-gpt-image-2`.

Coder provider catalog того же Hermes-Codex key дополнительно содержит
`gpt-5.4-mini`, Terra и Luna для tier-aware fallback.

## Выбор Byesu generator

| Качество | Референсы | Генератор |
|---|---:|---|
| 1K | 0–3 | `gpt-image-2` |
| 1K | 4–6 | `firefly-gpt-image-2` |
| 2K | 0–6 | `firefly-gpt-image-2` |
| 4K | 0–6 | `firefly-gpt-image-2` |

Качество 2K/4K само по себе никогда не переключает provider. Выбор provider
происходит только по dynamic availability flag.

## Production-конфигурация

```env
OPENAI_API_KEY=<Hermes-Codex key>
BYESU_HERMES_CODEX_API_KEY=<тот же Hermes-Codex key>
BYESU_MEDIA_GEN_API_KEY=<Media Gen key>

CODEX_AVAILABILITY_REFRESH_SECONDS=18000
CODEX_IMAGE_BYESU_FALLBACK_ENABLED=true
CODEX_IMAGE_BYESU_BASE_URL=https://byesu.com/v1
CODEX_IMAGE_BYESU_TIMEOUT_SECONDS=600
```

## Обязательные live smoke после rollout

1. Startup live probe создаёт persisted state отдельно для Velvet и Max.
2. `next_periodic_check_at - last_periodic_check_at` равен 18000 секунд.
3. Ручной `refresh` не сдвигает `next_periodic_check_at`.
4. При `codex_available=true` обычная coder-задача идёт Codex-first.
5. При `codex_available=false` обычная coder-задача пропускает Codex и идёт в configured Byesu route.
6. При `codex_available=true` GPT Image 2 1K/2K/4K использует Codex-first.
7. При `codex_available=false` GPT Image 2 не запускает Codex и использует Byesu image fallback.
8. Реальный `subscription_limit` немедленно переводит flag в false до следующего запроса.
9. Provider `resets_at` сохраняется как `codex_available_at`, когда он известен.
10. Дополнительный reset-time probe не сдвигает пятичасовой cadence.
11. Пятичасовой probe способен заметить ранний weekly reset и вернуть true раньше старого `resets_at`.
12. `hold --until auto` использует provider reset; explicit hold сохраняется между процессами.
13. `clear` выполняет live refresh и не форсирует true.
14. Codex 1K выполняет одну creative generation без high-res pass.
15. Codex 2K/4K выполняет одну creative generation + отдельный non-creative GPT export pass.
16. Hermes-Codex key видит Mini/Sol/Terra/Luna по соответствующим capability checks, Media Gen key видит обе image-модели.
17. Два физических Byesu key различаются.

CI проверяет state machine, routing contract, secret boundaries и export lifecycle.
Фактический provider quota state и ранний reset подтверждаются production smoke.
