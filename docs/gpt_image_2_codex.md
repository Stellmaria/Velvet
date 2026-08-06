# GPT Image 2 через Codex Plus с резервом Byesu

Функция добавляет в Ауф отдельную модель с отображаемым именем `GPT Image 2`.
Основной маршрут использует существующий изолированный Hermes/Codex runtime,
авторизованный через ChatGPT Plus. Единственный платный резервный маршрут
использует Byesu и включается только после чистого исчерпания лимита Codex до
первого фактического tool execution.

## Возможности

- режим `Только текст`: 0 референсов;
- режим `Фото + текст`: от 1 до 5 референсов;
- промт до 8000 символов, максимум два сообщения;
- анализ референсов выполняет Каэль без ручного назначения ролей;
- модель анализа: GPT-5.6 Sol, Terra или Luna;
- усилие анализа: low, medium, high, xhigh или max;
- ровно одна фактическая генерация без автоматической перегенерации;
- итоговый формат: JPEG quality 95;
- Telegram получает сжатый preview и отдельный оригинальный JPEG-документ;
- в подписи сохраняются снимки лимитов Codex до и после задачи, когда runtime
  возвращает эти данные.

## Маршрутизация

Штатная последовательность:

1. Codex Plus получает пользовательский промт, все референсы, выбранные
   Sol/Terra/Luna и reasoning effort.
2. Если Codex запускает `image_gen`, любой последующий сбой завершает задачу без
   автоматического provider fallback.
3. Если Codex завершается с подтверждённым `subscription_limit` до первого
   tool execution, Hermes выполняет один Byesu fallback.
4. Byesu GPT-5.6 анализирует пользовательский текст и все 1–5 референсов и
   возвращает один нормализованный generation prompt.
5. `firefly-gpt-image-2` получает этот prompt и те же референсы и создаёт ровно
   одно изображение.

Lifecycle-события `thread.started` и `turn.started` не считаются tool execution.
События command/file/MCP/dynamic tool execution, существующий artifact,
mutation evidence или неизвестный результат генерационного запроса блокируют
fallback. Это предотвращает двойную картинку и двойное списание.

## Честный выбор качества

Codex/ImageGen не предоставляет Velvet надёжный контракт нативных уровней
1K, 2K и 4K. Поэтому выбранное качество не является обещанием для основного
маршрута: его JPEG сохраняет нативное разрешение источника и при необходимости
только подрезается под выбранную пропорцию без апскейла.

Byesu `firefly-gpt-image-2` принимает размер запроса, поэтому Ауф снова показывает
1K, 2K и 4K с явной подписью `качество резерва Byesu`. Размер формируется из
качества и выбранной пропорции, например:

- 1K · 1:1 → `1024x1024`;
- 2K · 16:9 → `2048x1152`;
- 4K · 9:16 → `2160x3840`.

## Ключ и capability gate

Fallback использует существующий `BYESU_HERMES_CODEX_API_KEY` внутри Hermes.
Ключ не передаётся Telegram-боту, sandbox task payload или пользовательскому
контексту.

Перед анализом и генерацией runtime вызывает `GET /v1/models` и требует, чтобы
тот же token group видел одновременно:

- выбранный `gpt-5.6-sol`, `gpt-5.6-terra` или `gpt-5.6-luna`;
- `firefly-gpt-image-2`.

Byesu media endpoint обычно требует token group `media / media-gen`. Если
существующий coder token создан в другой группе, fallback завершится fail closed
до генерационного запроса с явной ошибкой capability mismatch. Нельзя молча
использовать другой секрет или понижать выбранную модель.

## Конфигурация бота

В `.env.server` бота:

```env
CODEX_IMAGE_ENABLED=true
CODEX_IMAGE_ROUTER_URL=http://hermes-coder-router:8878
CODEX_IMAGE_ROUTER_TOKEN=<тот же client token, что HERMES_CODER_ROUTER_CLIENT_TOKEN>
CODEX_IMAGE_TIMEOUT_SECONDS=3600
```

Функция выключена по умолчанию. При включении отсутствие или слишком короткое
значение `CODEX_IMAGE_ROUTER_TOKEN` блокирует запуск worker, чтобы запросы не
уходили через незащищённый маршрут.

## Конфигурация Hermes

В отдельном root-owned coder env:

```env
BYESU_HERMES_CODEX_API_KEY=<existing Byesu token>
CODEX_IMAGE_BYESU_FALLBACK_ENABLED=true
CODEX_IMAGE_BYESU_BASE_URL=https://byesu.com/v1
CODEX_IMAGE_BYESU_MODEL=firefly-gpt-image-2
CODEX_IMAGE_BYESU_TIMEOUT_SECONDS=600
```

Перед включением выполните capability smoke через `/v1/models`. Не записывайте
сам token или полный ответ с приватными account metadata в worklog.

## Анализ внешности для других фото-моделей

Nano Banana 2/Pro, Seedream 5 Pro и Wan 2.7/Pro уже получают обычный текстовый
`prompt` вместе с референсами. Поэтому перед ними можно добавить общий
provider-neutral анализатор:

1. Sol, Terra или Luna получает пользовательский текст и весь набор референсов.
2. Анализатор возвращает структурированную visual specification: устойчивые
   признаки внешности, одежду, аксессуары, композицию, стиль, отрицательные
   ограничения и итоговый generation prompt.
3. Итоговый prompt передаётся существующему provider adapter вместе с исходными
   референсами.

Downstream image-модель не видит скрытое reasoning GPT и не получает отдельный
«сверхпромт». Она учитывает анализ только в той мере, в какой Velvet явно
добавил его в provider prompt и передал соответствующие изображения. Рекомендуемый
контракт должен сохранять пользовательский текст отдельно, а анализ добавлять как
служебную visual specification, чтобы не подменять намерение пользователя.

Это расширение относится к отдельному bounded-срезу. Оно меняет стоимость и
поведение всех существующих фото-моделей, поэтому не включается автоматически
в provider fallback GPT Image 2.

## Развёртывание Hermes

После обновления нужно пересобрать и перезапустить:

1. `hermes-coder-router`, чтобы получить image endpoints;
2. `hermes-coder-velvet`, чтобы смонтировать `codex_image_runner.py` и
   `byesu_image_fallback.py`;
3. root-owned sandbox launcher, чтобы использовать обновлённый runtime contract;
4. Velvet Bot с указанными переменными окружения.

Package architecture inventory и reviewed exemptions обновляются вместе с
изменениями runtime, поэтому preflight проверяет фактический состав новой модели.

Перед включением в production выполните live smoke:

1. успешная штатная Codex-генерация без Byesu;
2. искусственный чистый `subscription_limit` до tool execution;
3. Byesu Luna/Terra/Sol с поддерживаемыми reasoning effort;
4. text-to-image 1K;
5. image-to-image с пятью референсами 2K и 4K;
6. capability mismatch на неверной token group без generation charge;
7. блокировка fallback после synthetic tool execution;
8. preview, оригинальный документ и фактические размеры JPEG.

CI не подтверждает доступность активной подписки, token group, стоимость или
фактический возврат средств провайдера. Эти проверки остаются обязательным
production smoke.
