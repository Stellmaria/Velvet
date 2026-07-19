# Сессия: перенос quality operations controllers в presentation

- Дата: 2026-07-19
- ID: `2026-07-19-p3c-quality-operations-controllers`
- Линия/фаза: Velvet Archive, P3C
- Статус: `завершено`
- Ветка: `agent/p3c-quality-operations-controllers`
- Базовый commit: `16811adefe4acc5d7cc2b2cce1b37cf989ea4ab2`

## Перед началом

### Цель

Перенести все прямые legacy Telegram-контроллеры bundle `quality_operations` из `velvet_bot/handlers` в канонический presentation-пакет без изменения AI-процессов, команд, callback contracts, порядка регистрации и пользовательского поведения.

### Исходный контекст

После слияния PR #205 bundle `core_operations` использует canonical presentation controllers, а PR #206 разрешил администратору открывать архивные изображения больше 20 МБ исходным файлом. Следующим записанным P3C-срезом оставался `quality operations presentation controllers`. Bundle содержал 13 прямых imports из legacy handlers.

### Планируемый объём

- создать пакет `presentation/telegram/routers/quality_operations_controllers/`;
- перенести 13 active controller implementations без переписывания исходного кода;
- заменить старые handler-файлы module aliases того же объекта;
- переключить bundle на canonical imports в прежнем порядке;
- сохранить команды, callback data, reply filters, AI job kinds и worker boundaries;
- сохранить monkeypatch-совместимость через identity legacy и canonical modules;
- обновить P3 router contract и architecture inventory;
- добавить regression-тесты module identity, canonical ownership и bundle composition;
- не менять SQL, миграции, application services, модели, конфигурацию Qwen и пользовательские тексты.

### Критерии готовности

- все 13 canonical modules содержат реальные Router implementations;
- legacy imports возвращают те же module objects и не содержат router decorators;
- bundle содержит 13 routers в прежнем порядке;
- active legacy implementations уменьшаются с 27 до 14;
- aliases увеличиваются с 41 до 54;
- общее число active bundle routers остаётся 56, дублей остаётся 0;
- полный tests, Docker build и project notes contract зелёные.

### Риски и ограничения

Контроллеры качества содержат крупные Qwen, Telegram download, media-set и background-worker flows. Поэтому они перенесены повторным использованием исходных Git blob SHA, а не ручным копированием. Legacy module aliases сохраняются для тестов, monkeypatch и временной обратной совместимости до P3D. Этот срез не занимается декомпозицией крупных файлов и не меняет бизнес-логику под видом архитектурной уборки.

## После завершения

### Фактически сделано

- создан пакет `velvet_bot/presentation/telegram/routers/quality_operations_controllers`;
- перенесены `backup_center`, `ai_jobs`, `quality_operations`, три `velvet_ai` controller, `quality_duplicates`, `quality_sets`, `quality_set_ai`, `quality_calibration`, `quality_ai_preview`, `quality_ai` и `quality_center`;
- canonical implementations используют исходные Git blob SHA без изменения содержимого;
- 13 legacy handler-файлов заменены module aliases;
- bundle переключён на canonical imports с исходным include order;
- source-path contracts AI flows и P3 router organization переведены на canonical paths;
- добавлен `tests/test_p3c_quality_operations_controllers.py`;
- architecture inventory обновлён до 14 implementations и 54 aliases;
- следующим P3C-срезом назначены оставшиеся archive-and-public controllers.

### Миграции и совместимость

Миграции PostgreSQL не требуются и не изменялись. Callback schemas, slash-команды, `AIJobTracker` kinds, Qwen configuration, worker names, Telegram reply markers, порядок routers и application boundaries сохранены. Старые import paths возвращают те же canonical module objects.

### Проверки

- tests #1019: success;
- Docker build #555: success;
- project notes contract #409: success;
- active bundle routers: 56, duplicate registrations: 0;
- active legacy implementations: 14, aliases: 54;
- первый полный CI прошёл без runtime и source-path regressions.

### PR и commit

- PR: #207 `Move quality operations controllers into presentation`;
- рабочая ветка: `agent/p3c-quality-operations-controllers`;
- runtime move commit: `b9949b9f34b79358db6cce84b897ff53535d6160`;
- проверенный runtime head: `31e12ec5eec3b223a2cfd1ae57b88474a8629d9e`.

### Незавершённое

В `archive_and_public` остаются прямые legacy controllers; они требуют следующего отдельного P3C-среза, чтобы не смешивать архив, публикацию и служебные команды с Qwen-контроллерами. Временные aliases остаются контролируемым остатком до P3D.

### Следующий шаг

Слить PR #207 после зелёного CI финального documentation head. Затем продолжить remaining archive-and-public presentation controllers с актуального `main`.
