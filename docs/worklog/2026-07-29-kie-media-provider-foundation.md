# 2026-07-29 — Kie, референсы и интерфейс Мяу

- Дата: 2026-07-29
- ID: kie-media-provider-foundation
- Линия/фаза: Линия B — Velvet AI / media generation
- Статус: `готово к review`
- Ветка: `agent/kie-media-provider-foundation`
- Базовый commit: `de9d59441aabbae1c888da65be26932588fd62e4`

## Перед началом

### Цель

Добавить owner-only фото-генерацию через Kie.ai под кнопкой «Мяу»: текст, до пяти референсов из базы или Telegram, проверка запроса, выбор Nano Banana Pro / Seedream 5 Pro, модель-зависимое качество, mature-режим и безопасный платный запуск через общую PostgreSQL-очередь.

### Исходный контекст

В проекте уже существовали PostgreSQL lifecycle AI-задач, budget ledger, библиотека `character_references` и owner-контроль расходов. Первый срез PR добавил Kie provider foundation, но работал только с текстовым промтом. Для реальной генерации по внешности нужно было провести Telegram `file_id` через скачивание байтов и временную загрузку в Kie File Upload API, не создавая вторую базу референсов рядом с существующей.

### Планируемый объём

- сохранить кнопку с точным названием «Мяу» в каноническом owner home;
- добавить корневые действия «Создать» и «Оживить»;
- реализовать фото-режимы «Текст», «Фото», «Фото + текст»;
- разрешить смешивать до пяти сохранённых и присланных Telegram-референсов;
- выбирать референсы из `character_references` по персонажам с листанием;
- принимать Telegram photo и image document JPG, PNG или WEBP до 10 МБ;
- показывать экран проверки с кнопками «Да, подтвердить», «Изменить», «Отмена»;
- после подтверждения предлагать только Nano Banana Pro и Seedream 5 Pro;
- показывать 1K / 2K / 4K только там, где модель это поддерживает;
- включить mature-режим по умолчанию без выдумывания неподдерживаемых provider flags;
- скачивать Telegram-файлы worker-ом и загружать их во временное Kie-хранилище;
- вызывать provider только после повторной атомарной проверки бюджета;
- покрыть flow, payload, upload и worker unit-тестами без платных live calls.

### Критерии готовности

- UI содержит точные пользовательские действия из ТЗ;
- экран проверки имеет ровно три обязательные кнопки;
- модель нельзя выбрать до проверки запроса;
- качество нельзя выбрать до выбора модели;
- выбор качества создаёт `media.generate.kie` только после проверки бюджета;
- очередь хранит Telegram reference descriptors, а не истекающие provider URLs;
- worker скачивает каждый `file_id`, загружает байты в Kie и подставляет полученные URL;
- Nano Banana Pro получает `image_input`, Seedream получает `image_urls`;
- Seedream mature request передаёт `nsfw_checker=false`;
- Nano Banana Pro не получает выдуманный safety parameter;
- ошибка Telegram delivery не повторяет платный provider call;
- unit tests, mypy, Docker build и project notes contract проходят.

### Риски и ограничения

- точный model id Seedream 5 Pro должен быть проверен в кабинете Kie и задан через `KIE_SEEDREAM_5_PRO_MODEL`;
- Nano Banana Pro не публикует отдельный API-флаг отключения moderation, поэтому mature-режим не отменяет policy самого provider;
- «Оживить» в этом срезе является видимой точкой входа с сообщением о следующем video-срезе, без скрытого запуска Grok;
- временные Kie upload URLs создаются непосредственно перед генерацией и не сохраняются в queue payload;
- provider result пока доставляется по CDN URL и не копируется в постоянное собственное хранилище;
- live Kie calls в CI запрещены.

## После завершения

### Фактически сделано

- добавлены `KieInputMode`, `KieContentMode` и `KieReferenceImage`;
- queue payload хранит режим, текст, content mode и до пяти Telegram reference descriptors;
- реализованы проверки обязательного текста / фото для каждого режима;
- Nano Banana Pro поддерживает 1K, 2K и 4K;
- Seedream 5 Pro поддерживает 1K и 2K в текущем UI;
- photo-only flow получает внутренний provider prompt, поскольку API требует непустой prompt;
- Seedream mature payload передаёт `nsfw_checker=false`;
- добавлен Kie Base64 File Upload client и отдельный `KIE_FILE_UPLOAD_BASE_URL`;
- worker скачивает Telegram-файлы с retry и timeout, проверяет лимит 10 МБ и загружает их в Kie;
- worker обновляет heartbeat после каждого reference upload и во время provider polling;
- реализован выбор сохранённых референсов из `character_references` по персонажам;
- реализовано добавление и удаление референса с визуальным листанием;
- можно смешивать библиотечные и новые Telegram-фото в одной задаче;
- подпись Telegram-фото может стать промтом режима «Фото + текст»;
- реализован полный FSM: режим → ввод → проверка → модель → качество → очередь;
- экран проверки содержит ровно «Да, подтвердить», «Изменить», «Отмена»;
- в model picker доступны только Nano Banana Pro и Seedream 5 Pro;
- кнопка «Оживить» не выполняет платных действий и сообщает о следующем этапе;
- Kie включается только через серверный env и остаётся выключенным по умолчанию.

### Миграции и совместимость

Миграции не добавлялись. Используются существующие `character_references`, `ai_tasks` и `ai_usage_events`. Очередь хранит устойчивые Telegram `file_id`, поэтому provider URL не успевает протухнуть до claim. При `KIE_ENABLED=false` worker не регистрируется и платные вызовы невозможны.

### Проверки

На кодовом head `aa7f9d8831ff392f140c43fa7f501fb1386f3647` успешно прошли:

- tests workflow `#2144`: 1508 тестов;
- type check `#797`;
- Docker build `#1522`;
- project notes contract `#1380`.

Первый прогон нового flow прошёл все 1508 кодовых тестов и упал только на устаревшем navigation inventory; счётчик обновлён с 875 до 910 кнопок. Реальные Kie-запросы и списания не выполнялись.

### PR и commit

- PR: `#355` — «Добавить Kie, референсы и интерфейс Мяу»;
- ветка: `agent/kie-media-provider-foundation`;
- проверенный кодовый head: `aa7f9d8831ff392f140c43fa7f501fb1386f3647`;
- базовый commit: `de9d59441aabbae1c888da65be26932588fd62e4`.

### Незавершённое

- подтвердить точный provider model id Seedream 5 Pro в кабинете Kie;
- выполнить одиночные live smoke tests Nano Banana Pro и Seedream 5 Pro;
- проверить реальные provider payload differences для text-to-image и image edit после live smoke;
- нормализовать редкие Telegram image documents с generic MIME при необходимости;
- копировать готовые provider results в постоянное собственное хранилище;
- реализовать ветку «Оживить» с отдельной video model и image-to-video flow.

### Следующий шаг

После слияния PR заполнить серверные `KIE_API_KEY`, `KIE_USD_TO_RUB`, `KIE_SEEDREAM_5_PRO_MODEL`, включить Kie и провести по одной owner-only генерации: текстовая Nano Banana Pro, reference Nano Banana Pro и reference Seedream 5 Pro. После проверки реальных ответов перейти к постоянному сохранению результатов и ветке «Оживить».
