# 2026-07-29 — Kie provider и интерфейс Мяу

- Дата: 2026-07-29
- ID: kie-media-provider-foundation
- Линия/фаза: Линия B — Velvet AI / media generation
- Статус: `частично`
- Ветка: `agent/kie-media-provider-foundation`
- Базовый commit: `de9d59441aabbae1c888da65be26932588fd62e4`

## Перед началом

### Цель

Добавить безопасную личную генерацию изображений и видео через Kie.ai, подключённую к общей PostgreSQL-очереди и AI-бюджету, с owner-only Telegram-интерфейсом под кнопкой «Мяу».

### Исходный контекст

В проекте уже существуют PostgreSQL lifecycle AI-задач, бюджетный ledger и owner-контроль расходов. При этом адаптера генеративного media provider и пользовательского интерфейса ещё не было. Прямой вызов Kie из Telegram handler создал бы второй независимый lifecycle без атомарного claim, retry, heartbeat и повторной проверки бюджета непосредственно перед списанием.

### Планируемый объём

- добавить внутренние alias для Seedream 5 Pro, Nano Banana Pro и Grok Imagine Video;
- отделить стабильные внутренние имена моделей от provider model id;
- добавить model-specific payload builders и сериализацию queue payload;
- рассчитывать себестоимость в USD и рублях без пользовательской наценки;
- реализовать асинхронный Kie client поверх stdlib HTTP;
- поддержать createTask, recordInfo, polling, timeout и transient backoff;
- подключить `media.generate.kie` к существующей PostgreSQL-очереди;
- резервировать общий AI-бюджет непосредственно перед provider call;
- добавить heartbeat долгой генерации и terminal retry lifecycle;
- добавить owner-only интерфейс «Мяу»: модель, промт, цена, подтверждение;
- доставлять готовое фото или видео в Telegram без повторного платного вызова при ошибке доставки;
- покрыть новый срез unit-тестами без реальных платных запросов.

### Критерии готовности

- кнопка называется ровно «Мяу» и видна только в каноническом owner home;
- интерфейс предлагает Seedream 5 Pro, Nano Banana Pro и Grok Imagine Video;
- неизвестный Seedream model id не подменяется выдуманным значением;
- до подтверждения платный запрос не выполняется;
- подтверждение создаёт `media.generate.kie` в общей очереди;
- worker атомарно claim-ит только задачи Kie;
- бюджет проверяется повторно и резервируется непосредственно перед provider call;
- polling возвращает URL результата и списанные кредиты;
- heartbeat защищает долгую генерацию от stale recovery;
- ошибка Telegram delivery не запускает генерацию повторно;
- unit-тесты, mypy, Docker build и project notes contract проходят.

### Риски и ограничения

- точный model id Seedream 5 Pro должен быть проверен в кабинете Kie и задан через `KIE_SEEDREAM_5_PRO_MODEL`;
- live-вызовы Kie в CI запрещены;
- `KIE_USD_TO_RUB` обновляется вручную в серверном `.env`, чтобы бюджетный расчёт не зависел от скрытого внешнего FX-запроса;
- первая версия «Мяу» использует безопасные пресеты 9:16 без загрузки Telegram-референсов;
- provider CDN URL пока доставляется напрямую в Telegram и не сохраняется в постоянное собственное хранилище;
- реальная стоимость записывается по предварительной тарифной оценке, пока Kie не предоставляет надёжную денежную сумму в recordInfo.

## После завершения

### Фактически сделано

- добавлен domain `media_generation` со стабильными alias трёх целевых моделей;
- добавлен `KieModelCatalog`, отделяющий внутренние alias от provider model id;
- добавлены payload builders и round-trip сериализация для PostgreSQL queue payload;
- добавлен расчёт себестоимости в USD и рублях без наценки;
- реализован асинхронный `KieClient` с createTask, recordInfo, polling и timeout;
- добавлены transient backoff, protocol validation и typed terminal task error;
- добавлен `KieGenerationWorker`, claim-ящий только `media.generate.kie`;
- worker использует единый `AIRequestExecutor`, budget reservation и usage ledger;
- во время долгого provider polling worker обновляет heartbeat queue lock;
- успешная задача завершается до best-effort Telegram delivery, поэтому сбой доставки не повторяет платный вызов;
- добавлен owner-only FSM-интерфейс «Мяу» с выбором модели, промтом, стоимостью и подтверждением;
- в канонический owner home добавлена кнопка с точным текстом «Мяу»;
- Kie settings передаются через bootstrap, worker composition и dispatcher workflow data;
- worker регистрируется только при `KIE_ENABLED=true`;
- добавлен обязательный ручной `KIE_USD_TO_RUB` для рублёвого budget guard;
- добавлены тесты provider lifecycle, pricing, queue payload, UI-контракта и worker delivery.

### Миграции и совместимость

Миграции базы данных не добавлялись: используется существующая таблица `ai_tasks` и общий usage ledger. При `KIE_ENABLED=false` Kie worker не регистрируется, платные вызовы невозможны, а кнопка «Мяу» показывает состояние настройки. Существующие AI, archive и workspace flows не меняют свои provider contracts.

### Проверки

- первый provider-only head прошёл 1495 тестов, mypy, Docker build и project notes contract;
- для второго среза добавлены новые unit-тесты UI и worker lifecycle;
- финальный GitHub Actions прогон запускается после обновления worklog и navigation inventory;
- реальные Kie-запросы и списания не выполнялись.

### PR и commit

- PR: `#355` — «Добавить фундамент Kie media provider»;
- ветка: `agent/kie-media-provider-foundation`;
- PR временно возвращён в draft на время расширения среза;
- базовый commit: `de9d59441aabbae1c888da65be26932588fd62e4`.

### Незавершённое

- подтвердить точный provider model id Seedream 5 Pro в кабинете Kie;
- добавить загрузку одного или нескольких Telegram-референсов в доступное Kie хранилище;
- сохранять provider result в постоянное собственное хранилище до истечения CDN URL;
- расширить «Мяу» настройками разрешения, длительности и качества после live API-smoke;
- провести контролируемый live smoke после добавления серверных `KIE_API_KEY`, `KIE_USD_TO_RUB` и Seedream model id.

### Следующий шаг

После зелёного CI и слияния PR настроить серверный `.env`, выполнить одиночный owner-only live smoke Nano Banana Pro, затем добавить безопасную загрузку Telegram-референсов и постоянное сохранение результатов.
