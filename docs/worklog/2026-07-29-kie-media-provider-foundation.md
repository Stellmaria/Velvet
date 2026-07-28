# 2026-07-29 — фундамент Kie media provider

- Дата: 2026-07-29
- ID: kie-media-provider-foundation
- Линия/фаза: Линия B — Velvet AI / media generation
- Статус: `частично`
- Ветка: `agent/kie-media-provider-foundation`
- Базовый commit: `de9d59441aabbae1c888da65be26932588fd62e4`

## Перед началом

### Цель

Добавить безопасный transport-neutral фундамент для личной генерации изображений и видео через Kie.ai без Telegram UI, реальных provider calls и списаний в CI.

### Исходный контекст

В проекте уже существуют PostgreSQL lifecycle AI-задач, бюджетный ledger и owner-контроль расходов. При этом адаптера генеративного media provider ещё нет, а прямое встраивание HTTP-вызовов Kie в Telegram handlers создало бы второй независимый lifecycle без dedupe, retry и нормального учёта стоимости.

### Планируемый объём

- добавить внутренние alias для Seedream 5 Pro, Nano Banana Pro и Grok Imagine video;
- отделить стабильные внутренние имена моделей от provider model id;
- добавить model-specific payload builders;
- рассчитывать себестоимость в USD без пользовательской наценки;
- реализовать асинхронный Kie client поверх stdlib HTTP;
- поддержать createTask, recordInfo, polling, timeout и transient backoff;
- добавить typed protocol, provider и terminal task errors;
- добавить отдельный env-контракт `KIE_*`;
- покрыть новый срез unit-тестами без реальных платных вызовов.

### Критерии готовности

- Nano Banana Pro и Grok используют подтверждённые provider model id;
- неизвестный Seedream 5 Pro model id не подменяется выдуманным значением;
- клиент создаёт задачу и извлекает `taskId`;
- polling возвращает URL результата и списанные кредиты;
- terminal failure поднимает typed exception;
- transient provider errors допускают backoff;
- себестоимость вычисляется детерминированно;
- unit-тесты, mypy, Docker build и project notes contract проходят.

### Риски и ограничения

- точный model id Seedream 5 Pro должен быть проверен в кабинете Kie и задан через `KIE_SEEDREAM_5_PRO_MODEL`;
- live-вызовы Kie в CI запрещены;
- загрузка Telegram-референсов и собственное файловое хранилище не входят в этот срез;
- подключение к `ai_tasks`, budget ledger и Telegram-командам остаётся следующим этапом;
- текущие ориентиры стоимости хранятся в USD и могут быть изменены через env без правки кода.

## После завершения

### Фактически сделано

- добавлен domain `media_generation` со стабильными alias трёх целевых моделей;
- добавлен `KieModelCatalog`, отделяющий внутренние alias от provider model id;
- добавлены payload builders для Seedream, Nano Banana Pro и Grok Imagine video;
- добавлен расчёт себестоимости без наценки для разрешения, качества и длительности;
- реализован асинхронный `KieClient` с createTask, recordInfo, polling и timeout;
- добавлены transient backoff, protocol validation и typed terminal task error;
- добавлен отдельный `load_kie_settings()` и полный `.env.example` контракт;
- Seedream model id намеренно оставлен обязательным внешним параметром;
- добавлены unit-тесты payload, pricing, success, failure и env validation.

### Миграции и совместимость

Миграции базы данных не добавлялись. Новая интеграция выключена по умолчанию через `KIE_ENABLED=false`, не меняет существующий composition root и не выполняет provider calls до явной настройки серверного `.env`.

### Проверки

- локально прошли 6 unit-тестов нового модуля;
- локально прошёл `compileall` нового среза;
- GitHub Actions Docker build прошёл;
- первая проверка mypy выявила один небезопасный `object → int`, исправленный отдельным commit;
- первая проверка project notes выявила неполный шаблон worklog, исправленный отдельным commit;
- повторные проверки CI запускаются после исправлений;
- реальные Kie-запросы и списания не выполнялись.

### PR и commit

- PR: `#355` — «Добавить фундамент Kie media provider»;
- ветка: `agent/kie-media-provider-foundation`;
- базовый commit: `de9d59441aabbae1c888da65be26932588fd62e4`.

### Незавершённое

- подтвердить точный provider model id Seedream 5 Pro в кабинете Kie;
- подключить Kie provider к `ai_tasks` и единому budget executor;
- добавить owner-only Telegram UI с предварительным показом себестоимости;
- загрузить Telegram-референсы во временное внешнее хранилище;
- скачивать и сохранять provider result до истечения CDN-ссылки;
- провести контролируемый live smoke после добавления серверного `KIE_API_KEY`.

### Следующий шаг

Добавить queue consumer для `media.generate`, owner-only команды с предварительным показом себестоимости, загрузку референсов и сохранение результата в собственное хранилище до отправки в Telegram.
