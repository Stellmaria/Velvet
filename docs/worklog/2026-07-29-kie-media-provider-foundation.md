# 2026-07-29 — фундамент Kie media provider

- Дата: 2026-07-29
- ID: kie-media-provider-foundation
- Линия/фаза: Линия B — Velvet AI / media generation
- Статус: `частично`
- Ветка: `agent/kie-media-provider-foundation`
- Базовый commit: `de9d59441aabbae1c888da65be26932588fd62e4`

## Цель

Добавить безопасный transport-neutral фундамент для личной генерации изображений и видео через Kie.ai без Telegram UI, реальных provider calls и списаний в CI.

## Объём среза

- внутренние alias для Seedream 5 Pro, Nano Banana Pro и Grok Imagine video;
- model catalog с отдельным provider model id;
- payload builders для image и video generation;
- оценка себестоимости в USD без пользовательской наценки;
- асинхронный Kie client поверх stdlib HTTP;
- createTask, recordInfo, polling, timeout и transient backoff;
- typed protocol/provider/task errors;
- отдельная конфигурация KIE_*;
- unit-тесты payload, pricing, create/poll/success/failure и env validation.

## Ограничения

- точный model id Seedream 5 Pro намеренно не выдумывается и должен быть задан через `KIE_SEEDREAM_5_PRO_MODEL` после проверки в кабинете Kie;
- Nano Banana Pro использует документированный id `nano-banana-pro`;
- Grok video использует документированный id `grok-imagine/text-to-video`;
- этот PR не загружает Telegram-файлы во внешнее хранилище;
- этот PR не подключает Kie к `ai_tasks`, budget ledger или Telegram-командам;
- стоимость пока хранится в USD и будет конвертироваться в рубли только в следующем срезе через единый budget executor;
- live-вызовы Kie в CI запрещены.

## Следующий шаг

Добавить queue consumer для `media.generate`, owner-only команды с предварительным показом себестоимости, загрузку референсов и сохранение результата в собственное хранилище до отправки в Telegram.
