# Сессия: Seedance 1.5 Pro и Wan 2.6 в Оживить

- Дата: 2026-07-29
- ID: 2026-07-29-seedance-wan-video-models
- Линия/фаза: Мяу / генерация видео / несколько provider-моделей
- Статус: частично
- Ветка: agent/seedance-wan-video-models
- Базовый commit: d7b99638329e5905ac556fc357c0482e57972db0

## Перед началом

### Цель

Расширить `Мяу → Оживить`: сохранить дешёвый Grok Imagine v1, добавить Seedance 1.5 Pro с выбором генерации звука и Wan 2.6 с выбором качества и длительности. Все маршруты используют одно внешнее фото, текст движения и `nsfw_checker=false`.

### Подтверждённые provider-контракты

- Grok: `grok-imagine/image-to-video`, `image_urls`, prompt, 480p/720p.
- Seedance: `bytedance/seedance-1.5-pro`, `input_urls`, 480p/720p/1080p, duration, `fixed_lens`, `generate_audio`, `nsfw_checker`.
- Wan: `wan/2-6-image-to-video`, ровно один `image_urls`, 720p/1080p, duration как строка, `nsfw_checker`.

### Планируемый UX

1. выбрать или загрузить фото;
2. написать текст движения;
3. выбрать Grok, Seedance или Wan;
4. выбрать параметры модели;
5. увидеть расчёт стоимости;
6. подтвердить платный запуск.

### Параметры

- Grok: 480p/720p, остальные provider defaults скрыты;
- Seedance: 480p/720p/1080p, 5 секунд, звук включён или выключен;
- Wan: 720p/1080p, 5/10/15 секунд.

### Безопасность и эксплуатация

- owner-only;
- AI budget guard до постановки задачи;
- session dedupe;
- максимум одно фото до 10 МБ;
- `nsfw_checker=false` во всех provider payload;
- результат скачивается worker-ом и отправляется в Telegram байтами;
- отсутствие гарантии обхода внутренних ограничений самих моделей.

## После завершения

### Фактически сделано

- расширены `KieModelAlias`, `KieModelCatalog` и `KiePricing`;
- добавлены provider payload для Seedance 1.5 Pro и Wan 2.6;
- Telegram-flow получил выбор модели и model-specific настройки;
- Seedance получил выбор со звуком/без звука;
- Wan получил выбор 720p/1080p и 5/10/15 секунд;
- тесты проверяют фактический JSON на границе Kie и расчёт стоимости.

### Незавершённое

- обновить `.env.example`;
- прогнать CI и исправить контрактные расхождения;
- обновить Telegram navigation inventory;
- выполнить живые платные smoke-тесты после обновления Supervisor.
