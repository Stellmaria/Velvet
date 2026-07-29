# Сессия: Seedance 1.5 Pro и Wan 2.6 в Оживить

- Дата: 2026-07-29
- ID: 2026-07-29-seedance-wan-video-models
- Линия/фаза: Мяу / генерация видео / несколько provider-моделей
- Статус: завершено
- Ветка: agent/seedance-wan-video-models
- Базовый commit: d7b99638329e5905ac556fc357c0482e57972db0

## Перед началом

### Цель

Расширить `Мяу → Оживить`: сохранить дешёвый Grok Imagine v1, добавить Seedance 1.5 Pro с выбором генерации звука и Wan 2.6 с выбором качества и длительности. Все маршруты используют одно внешнее фото, текст движения и `nsfw_checker=false`.

### Исходный контекст

После PR #364 production-flow поддерживал только `grok-imagine/image-to-video`. Фото, prompt и качество уже проходили через owner-only UI, AI budget guard, session dedupe, Kie upload и byte-based доставку MP4. Новые модели должны использовать ту же очередь и доставку, но имеют разные provider-поля и тарифы.

### Планируемый объём

- добавить alias и provider model id для Seedance 1.5 Pro и Wan 2.6;
- расширить доменный Kie payload без изменения существующих фото-моделей;
- добавить выбор Grok/Seedance/Wan после ввода prompt;
- дать Seedance выбор 480p/720p/1080p и звук включён/выключен;
- дать Wan выбор 720p/1080p и 5/10/15 секунд;
- сохранить `nsfw_checker=false`, budget guard, dedupe и доставку MP4;
- покрыть фактические provider payload тестами.

### Критерии готовности

- пользователь может выбрать одну из трёх video-моделей;
- Seedance отправляет `input_urls`, `generate_audio` и `nsfw_checker=false`;
- Wan отправляет один `image_urls`, duration строкой и `nsfw_checker=false`;
- review показывает точную конфигурацию и расчётную цену;
- повторное подтверждение не создаёт вторую платную задачу;
- tests, type check, Docker build и project notes contract проходят.

### Риски и ограничения

- публичная pricing-страница Kie не показывает полный тарифный ряд для Seedance и Wan в статическом HTML, поэтому тарифы вынесены в `.env` и могут обновляться без кода;
- `nsfw_checker=false` отключает дополнительный фильтр Kie, но не гарантирует обход внутренних ограничений исходной модели;
- Seedance получает одно фото, хотя provider допускает до двух;
- для Seedance длительность фиксируется на 5 сек в первом production-варианте;
- живой provider smoke-test является платным и выполняется только после deployment.

## После завершения

### Фактически сделано

- расширены `KieModelAlias`, `KieModelCatalog` и `KiePricing`;
- добавлены provider payload для Seedance 1.5 Pro и Wan 2.6;
- Telegram-flow получил выбор модели и model-specific настройки;
- Seedance получил выбор со звуком/без звука;
- Wan получил выбор 720p/1080p и 5/10/15 секунд;
- добавлен отдельный пример серверного env;
- пустые model env корректно используют документированные значения по умолчанию;
- navigation inventory обновлён до 958 inline-кнопок без нарушений;
- тесты проверяют фактический JSON на границе Kie и расчёт стоимости.

### Миграции и совместимость

Миграции базы данных не нужны. Существующая очередь хранит alias и восстанавливает запрос через `KieGenerationRequest.from_task_payload`. Старые Grok-задачи остаются совместимыми. Worker определяет видео через `model.is_video`, поэтому новые alias используют существующую загрузку референса и MP4-доставку.

### Проверки

На commit `afd21e98615eac472c337c74ad23849d759b8d01` успешно прошли:

- tests run `30440139291`: 1545 тестов, success;
- type check run `30440138930`: success;
- Docker build run `30440141835`: success;
- project notes contract run `30440139195`: success.

### PR и commit

- PR: #365 `Добавить Seedance 1.5 Pro и Wan 2.6 в Оживить`;
- ветка: `agent/seedance-wan-video-models`;
- проверенный функциональный head: `afd21e98615eac472c337c74ad23849d759b8d01`;
- merge commit будет записан GitHub после слияния.

### Незавершённое

Кодовая интеграция завершена. После deployment нужны три платных smoke-теста на текущем аккаунте Kie:

1. Seedance 480p, 5 сек, без звука;
2. Seedance 480p, 5 сек, со звуком;
3. Wan 720p, 5 сек.

Они подтвердят доступность моделей на аккаунте, фактическую тарификацию и формат возвращаемого MP4.

### Следующий шаг

Прогнать финальный CI после документационного commit, снять draft, проверить обсуждения PR, слить #365 в `main`, обновить Supervisor и выполнить дешёвые live smoke-тесты.
