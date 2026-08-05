# Сессия: GPT Image 2 через Codex Plus

- Дата: 2026-08-05
- ID: `2026-08-05-gpt-image-2-codex-plus`
- Линия/фаза: Auf media generation / Hermes Codex integration
- Статус: завершено
- Ветка: `feat/gpt-image-2-codex`
- Базовый commit: `5c41eb54b6c79749649d6d0e087c2e980af98338`

## Перед началом

### Цель

Добавить в Ауф модель с отображаемым именем `GPT Image 2`, которая создаёт
изображение через существующий Hermes/Codex runtime, авторизованный подпиской
ChatGPT Plus, и возвращает пользователю preview вместе с исходным JPEG-файлом.

### Исходный контекст

Ауф уже поддерживал внешние модели генерации изображений с референсами, промтом,
разрешением и соотношением сторон. Каэль и Hermes имели отдельный изолированный
Codex runtime для задач разработки, но не имели transport contract для
одноразовой генерации изображения и бинарной доставки результата.

### Планируемый объём

- режим `Только текст` с нулём референсов;
- режим `Фото + текст` с 1–5 общими референсами;
- промт до 8000 символов в одном или двух сообщениях;
- автоматический анализ назначения референсов Каэлем;
- выбор GPT-5.6 Sol, Terra или Luna;
- выбор reasoning effort `low`, `medium`, `high`, `xhigh` или `max`;
- выбор экспорта 1K, 2K или 4K и стандартной пропорции;
- ровно один вызов встроенного `image_gen` без автоматической перегенерации;
- JPEG quality 95, preview и исходный документ;
- снимки лимитов Codex до и после задачи, когда runtime их возвращает;
- защищённый маршрут через существующий Hermes router и sandbox launcher;
- тесты, документация и полный CI перед слиянием.

### Критерии готовности

- модель отображается в Ауф как `GPT Image 2`;
- текстовый режим принимает 0 референсов, фото-режим принимает 1–5;
- служебные параметры не уменьшают пользовательский лимит промта;
- задача создаётся с `max_attempts=1`;
- runtime требует ровно один итоговый image artifact;
- image-run не получает GitHub token;
- экспорт создаёт точный JPEG выбранного размера и пропорции;
- Telegram получает preview и исходный JPEG-документ;
- Sol, Terra, Luna и effort передаются в Codex runtime;
- package architecture inventory синхронизирован;
- обязательные CI checks проходят перед merge.

### Риски и ограничения

- встроенный ImageGen через Plus не подтверждает нативную генерацию в точном 4K;
- увеличение меньшего исходника до 4K повышает разрешение файла, но не создаёт
  отсутствующие нативные детали;
- CI не может подтвердить доступность `image_gen` у конкретной активной подписки;
- rate-limit snapshots могут отсутствовать в отдельных запусках Codex;
- feature должен оставаться выключенным до настройки router token и live smoke;
- сетевые повторы доставки не должны повторно запускать генерацию.

## После завершения

### Фактически сделано

- добавлен отдельный тип задачи `media.generate.codex_image`;
- в Ауф добавлен поток `GPT Image 2` с режимами текст и фото+текст;
- реализованы лимиты 0 либо 1–5 референсов, 8000 символов и два сообщения;
- пользователь выбирает Sol, Terra или Luna и reasoning effort;
- реализован выбор 1K, 2K или 4K и соотношения сторон;
- runtime требует один вызов встроенного `image_gen` и один итоговый artifact;
- задача использует `max_attempts=1`, автоматической перегенерации нет;
- image-run не получает GitHub token и работает в изолированном checkout;
- результат экспортируется в JPEG quality 95 через Lanczos и мягкий UnsharpMask;
- Telegram получает отдельный preview и исходный JPEG-документ;
- добавлены снимки лимитов Codex до и после задачи с безопасным fallback;
- добавлены router endpoints для статуса и бинарного результата;
- startup-порядок сохраняет финальный `install_auf_branding` guard;
- Hermes compose сохраняет immutable `requested_tier` routing contract;
- обновлены package architecture inventory и reviewed exemptions;
- добавлена эксплуатационная документация и regression-тесты.

### Миграции и совместимость

SQL-миграции и схема PostgreSQL не изменены. Функция выключена по умолчанию через
`CODEX_IMAGE_ENABLED=false`. Для включения нужны `CODEX_IMAGE_ROUTER_URL`,
`CODEX_IMAGE_ROUTER_TOKEN`, обновлённые coder router, Velvet coder runtime и
host sandbox launcher. Существующие Kie/GRS модели и их очереди не изменяются.

### Проверки

- targeted export tests покрывают 1K, 2K и 4K dimensions и JPEG output;
- runtime tests покрывают one-shot prompt, reference validation и artifact selection;
- Auf contract tests покрывают имя модели, task type и startup order;
- package architecture inventory с меткой `working-tree` успешно пересчитан;
- preflight выявил и после исправления проверяет финальный branding guard;
- Hermes routing contract восстановлен для immutable `requested_tier`;
- окончательный полный CI запускается на финальном head перед merge.

### PR и commit

- PR: #645 `Add GPT Image 2 generation through Codex Plus`;
- ветка: `feat/gpt-image-2-codex`;
- финальный squash commit будет создан GitHub при слиянии PR #645.

### Незавершённое

Кодовая реализация завершена. После deployment остаётся обязательный live smoke на
активной подписке Plus: текстовая генерация 1K, генерация с одним референсом,
проверка единственного вызова, preview, документа и доступных limit snapshots.

### Следующий шаг

Дождаться зелёных обязательных checks, слить PR #645 в `main`, затем обновить
production Hermes/Velvet runtime и выполнить описанный live smoke до включения
`CODEX_IMAGE_ENABLED=true` для пользователей.
