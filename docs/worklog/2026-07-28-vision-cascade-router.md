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

Работа начата.

### Миграции и совместимость

Планируется новая добавочная миграция кэша без изменения применённых файлов.

### Проверки

Будут выполнены unit/integration tests, type check, Docker build, project notes contract и backup restore drill.

### PR и commit

- PR: будет создан после завершения реализации и проверки diff.
- Ветка: `agent/vision-cascade-router`.

### Незавершённое

- metered client;
- cascade policy;
- PostgreSQL cache;
- worker integration;
- тесты и CI.

### Следующий шаг

Создать route models/cache repository и независимый metered vision client, затем подключить их к `MediaAIVisionService`.