# 2026-07-28 — каскадный VL router

- Дата: 2026-07-28
- ID: vision-cascade-router
- Линия/фаза: Линия B — Velvet AI / VL cascade
- Статус: `частично`
- Ветка: `agent/vision-cascade-router`
- Базовый commit: `d24aea889d74794f975497e705c5a5f4c7985d53`

## Перед началом

### Цель

Подключить смысловой анализ изображений к явному каскаду Flash → Pro → sensitive, транзакционному AI budget executor и PostgreSQL-кэшу, чтобы массовый анализ не вызывал дорогую модель без необходимости и не оплачивал повторно уже принятый результат.

### Исходный контекст

После PR #348–#351 существуют Hermes control plane, AI budget policy, PostgreSQL usage ledger, owner-команды бюджета и метеринг РП. Vision-задачи всё ещё используют `VisionClient` и глобальный model-routing compatibility layer: он перебирает модели при ошибке, но не принимает решение по confidence, не разделяет стоимость маршрутов и не создаёт постоянный кэш по содержимому изображения.

### Планируемый объём

- добавить явные роли `flash`, `pro`, `sensitive` поверх существующей vision-конфигурации;
- создать metered vision client с извлечением provider usage и консервативной оценкой при его отсутствии;
- запускать Pro только при низкой confidence или повреждённом результате Flash;
- запускать sensitive только по явному флагу либо при распознанном provider refusal;
- сохранить принятый результат в PostgreSQL-кэше по SHA-256, analysis type, model и prompt version;
- повторно использовать принятый кэш без provider call и новой резервации бюджета;
- интегрировать каскад в worker смыслового анализа `media_ai_profiles` без изменения остальных VL-задач;
- сохранять фактический provider/model/route в профиле;
- добавить pricing env, migration, unit и PostgreSQL integration tests.

### Критерии готовности

- Flash с достаточной confidence завершает запрос без Pro;
- низкая confidence Flash вызывает Pro, но не sensitive;
- provider refusal переходит на sensitive;
- явный sensitive mode не вызывает Flash и Pro;
- каждый реальный provider call имеет отдельную reservation и usage event;
- повтор того же изображения с тем же prompt/model contract возвращается из PostgreSQL-кэша;
- compatibility model routing не подменяет модели внутри явного каскада;
- worker записывает итоговый model и route;
- tests, type check, Docker build, project notes contract и backup restore drill проходят.

### Риски и ограничения

- конкретные model ID и цены остаются server env до живой проверки `/v1/models`;
- автоматическая предварительная NSFW-классификация не добавляется: sensitive используется по явному режиму или распознанному refusal;
- judge-модель для конфликта Flash/Pro остаётся следующим срезом;
- `ai_tasks` worker/claim API не входит в этот PR и будет подключён после стабилизации каскада;
- остальные старые vision-клиенты временно сохраняют compatibility routing.

## После завершения

### Фактически сделано

- добавлен domain `vision_routing` с маршрутами `flash`, `pro` и `sensitive`;
- Flash принимает результат при достаточной confidence, а низкая confidence переводит задачу на Pro;
- provider refusal Flash или Pro переводит задачу на sensitive при наличии настроенного маршрута;
- явный sensitive mode не вызывает Flash и Pro;
- metered VL client резервирует максимальную оценочную стоимость до provider call;
- OpenAI-compatible и Ollama usage извлекаются из ответа, а при отсутствии usage применяются консервативные оценки;
- каждый реальный route создаёт отдельную запись `ai_usage_events`;
- добавлен PostgreSQL-кэш по SHA-256, analysis type, model и prompt version;
- cache hit не вызывает provider и не резервирует новый бюджет;
- итоговые provider, model, route, content hash и cache-hit сохраняются в `media_ai_profiles`;
- semantic worker переключён на новый router через адаптер без переписывания его download/retry/error lifecycle;
- compatibility model routing блокируется от скрытой замены Flash-модели на Pro или sensitive;
- один audited `AIUsageService` разделяется между RP, VL workers и owner-командами;
- добавлен env-контракт для моделей, endpoint, attempts и pricing каждой роли;
- добавлены unit tests ветвей каскада, metered client, model isolation и PostgreSQL cache;
- cache persistence adapter размещён в domain `cache.py`, аналогично существующему AI ledger, поэтому закрытый P3E repository-layout baseline не расширялся искусственно.

### Миграции и совместимость

Добавлена новая неизменяемая миграция `migrations/z006_ai_vision_cache.sql`. Она создаёт `ai_vision_cache` и добавляет в `media_ai_profiles` поля `analysis_route`, `content_hash` и `cache_hit`. Старые миграции не изменены. Backup/restore drill подтвердил применение и восстановление схемы. При `AI_VISION_ENABLED=false` новые настройки не загружаются. Локальный Ollama получает нулевую API-стоимость; облачные маршруты требуют настроенного pricing.

### Проверки

На head `62254baa43c747c1ad0e70c9efee2d01c4aac4ec` успешно прошли:

- tests workflow `#2081`: 1479 тестов;
- type check `#734`;
- Docker build `#1460`;
- project notes contract `#1319`;
- backup restore drill `#463`.

Live-вызовы платных VL-провайдеров и production Telegram-smoke намеренно не выполнялись в CI.

### PR и commit

- PR: `#352` — «Добавить каскадный Flash Pro sensitive VL router».
- Ветка: `agent/vision-cascade-router`.
- Проверенный head: `62254baa43c747c1ad0e70c9efee2d01c4aac4ec`.

### Незавершённое

- живой API-тест конкретных Flash, Pro и sensitive model ID и цен;
- production-smoke semantic worker и проверка записей `analysis_route`/`cache_hit`;
- предварительный автоматический classifier чувствительного контента;
- judge route при конфликте Flash и Pro;
- `ai_tasks` claim/worker API и пакетная постановка задач;
- показ cache statistics в owner-интерфейсе;
- перевод остальных специализированных VL-клиентов с compatibility routing.

### Следующий шаг

Реализовать PostgreSQL `ai_tasks` claim/worker lifecycle, пакетную постановку смыслового анализа с предварительной оценкой максимального бюджета и owner-подтверждением запуска партии.